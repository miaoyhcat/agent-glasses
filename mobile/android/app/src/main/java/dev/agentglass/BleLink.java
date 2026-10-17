package dev.agentglass;

import android.Manifest;
import android.annotation.SuppressLint;
import android.bluetooth.*;
import android.bluetooth.le.*;
import android.content.Context;
import android.graphics.*;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.util.Base64;
import org.json.JSONObject;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/** One GATT write at a time; OS bonding plus application HMAC. Never sends code. */
@SuppressLint("MissingPermission")
public final class BleLink implements AutoCloseable {
    public interface Listener {void message(JSONObject message);void status(String text);}
    private final Context context;private final Listener listener;
    private final TaskDispatch writer=new TaskDispatch("gatt-write",16);
    private BluetoothGatt gatt;private BluetoothGattCharacteristic rx;
    private final StringBuilder incoming=new StringBuilder();
    private volatile String session;private String sendSession;private long seq=0;private byte[] key;private volatile int writePayload=20;
    private volatile CountDownLatch written;private volatile int writeStatus;
    private byte[] speech;private int speechOffset;
    private static final UUID SERVICE=UUID.fromString("6e400001-b5a3-f393-e0a9-e50e24dcca9e"),RX=UUID.fromString("6e400002-b5a3-f393-e0a9-e50e24dcca9e"),TX=UUID.fromString("6e400003-b5a3-f393-e0a9-e50e24dcca9e");
    public BleLink(Context c,Listener l){context=c;listener=l;}
    public void connect(String address,String keyHex)throws Exception{
        if(!keyHex.matches("[0-9a-fA-F]{64}"))throw new SecurityException("眼镜需要 32 字节 USB 配置密钥");
        key=new byte[32];for(int i=0;i<32;i++)key[i]=(byte)Integer.parseInt(keyHex.substring(i*2,i*2+2),16);
        BluetoothManager manager=(BluetoothManager)context.getSystemService(Context.BLUETOOTH_SERVICE);
        if(manager==null||manager.getAdapter()==null||!manager.getAdapter().isEnabled())throw new IllegalStateException("请打开蓝牙");
        BluetoothDevice d=manager.getAdapter().getRemoteDevice(address);
        if(d.getBondState()!=BluetoothDevice.BOND_BONDED)d.createBond();
        gatt=d.connectGatt(context,false,callbacks,BluetoothDevice.TRANSPORT_LE);
    }
    private final BluetoothGattCallback callbacks=new BluetoothGattCallback(){
        public void onConnectionStateChange(BluetoothGatt g,int status,int state){
            if(status==BluetoothGatt.GATT_SUCCESS&&state==BluetoothProfile.STATE_CONNECTED){writePayload=20;if(!g.requestMtu(247))g.discoverServices();listener.status("蓝牙已连接，协商数据包并等待系统加密绑定");}
            else if(state==BluetoothProfile.STATE_DISCONNECTED||status!=BluetoothGatt.GATT_SUCCESS){session=null;rx=null;writer.clearQueued();if(written!=null)written.countDown();listener.status("眼镜已断开，缓存保留；请重连");}
        }
        public void onMtuChanged(BluetoothGatt g,int mtu,int status){
            writePayload=status==BluetoothGatt.GATT_SUCCESS?Math.max(20,Math.min(180,mtu-3)):20;g.discoverServices();
        }
        public void onServicesDiscovered(BluetoothGatt g,int status){
            if(status!=BluetoothGatt.GATT_SUCCESS){listener.status("蓝牙服务发现失败，请重连");return;}
            BluetoothGattService service=g.getService(SERVICE);if(service==null){listener.status("设备协议不匹配");return;}
            rx=service.getCharacteristic(RX);BluetoothGattCharacteristic tx=service.getCharacteristic(TX);
            if(rx==null||tx==null||!g.setCharacteristicNotification(tx,true)){rx=null;listener.status("眼镜缺少收发特征或通知不可用");return;}
            BluetoothGattDescriptor d=tx.getDescriptor(UUID.fromString("00002902-0000-1000-8000-00805f9b34fb"));if(d==null){rx=null;listener.status("眼镜缺少通知描述符");return;}
            d.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);g.writeDescriptor(d);
        }
        public void onDescriptorWrite(BluetoothGatt g,BluetoothGattDescriptor d,int status){
            if(status!=BluetoothGatt.GATT_SUCCESS){listener.status("通知订阅失败，请完成系统绑定后重连");return;}
            BluetoothGattService s=g.getService(SERVICE);if(s==null||s.getCharacteristic(TX)==null||!g.readCharacteristic(s.getCharacteristic(TX)))listener.status("无法读取眼镜握手，请重连");
        }
        public void onCharacteristicRead(BluetoothGatt g,BluetoothGattCharacteristic c,int status){if(status==BluetoothGatt.GATT_SUCCESS)receive(c.getValue());}
        public void onCharacteristicChanged(BluetoothGatt g,BluetoothGattCharacteristic c){receive(c.getValue());}
        public void onCharacteristicWrite(BluetoothGatt g,BluetoothGattCharacteristic c,int status){writeStatus=status;if(written!=null)written.countDown();}
    };
    private synchronized void receive(byte[] value){
        if(value==null)return;
        for(byte b:value){char c=(char)(b&255);if(c=='\n'){
            String line=incoming.toString();incoming.setLength(0);
            try{JSONObject j=new JSONObject(line);if("hello".equals(j.optString("type"))){String next=j.getString("session");if(!next.matches("[0-9a-f]{32}"))throw new SecurityException();session=next;listener.status("眼镜握手成功 / "+j.optString("profile"));}
                if("speaker_ack".equals(j.optString("type")))speakerChunk(j.getInt("offset"));listener.message(j);
            }catch(Exception e){listener.status("眼镜消息解析失败");}
        }else{incoming.append(c);if(incoming.length()>=8192){incoming.setLength(0);listener.status("眼镜消息过长");}}}
    }
    public boolean ready(){return session!=null&&rx!=null;}
    public void send(JSONObject body){if(!writer.offer(()->writeFrame(body)))listener.status("BLE 操作已满，未发送；媒体原件保留，请重试");}
    private void writeFrame(JSONObject body){try{
        if(!ready())throw new IllegalStateException("眼镜尚未握手");String payload=body.toString(),sid=session;if(!sid.equals(sendSession)){seq=0;sendSession=sid;}long serial=++seq;
        String signed=sid+"\n"+serial+"\n"+payload;Mac mac=Mac.getInstance("HmacSHA256");mac.init(new SecretKeySpec(key,"HmacSHA256"));
        JSONObject envelope=new JSONObject().put("v",1).put("seq",serial).put("body",payload).put("mac",TlsApi.hex(mac.doFinal(signed.getBytes(StandardCharsets.UTF_8))));
        byte[] frame=envelope.toString().concat("\n").getBytes(StandardCharsets.UTF_8);
        if(frame.length>=4096)throw new IllegalArgumentException("帧过大");
        int packetSize=writePayload;
        for(int i=0;i<frame.length;i+=packetSize){byte[] part=Arrays.copyOfRange(frame,i,Math.min(frame.length,i+packetSize));written=new CountDownLatch(1);writeStatus=-1;
            rx.setWriteType(BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT);rx.setValue(part);
            if(!gatt.writeCharacteristic(rx)||!written.await(5,TimeUnit.SECONDS)||writeStatus!=BluetoothGatt.GATT_SUCCESS)throw new IllegalStateException("BLE 写入失败");
        }
    }catch(Exception e){listener.status(e.getMessage());}}
    public void hud(String text){try{
        Bitmap image=Bitmap.createBitmap(128,64,Bitmap.Config.ARGB_8888);Canvas canvas=new Canvas(image);canvas.drawColor(Color.BLACK);
        Paint paint=new Paint();paint.setColor(Color.WHITE);paint.setTextSize(14);paint.setTypeface(Typeface.create("sans-serif",Typeface.NORMAL));paint.setAntiAlias(false);
        int y=14;for(String raw:text.split("\n")){String line=raw;while(!line.isEmpty()&&y<=64){int count=paint.breakText(line,true,126,null);if(count<1)break;canvas.drawText(line.substring(0,count),1,y,paint);line=line.substring(count);y+=16;}if(y>64)break;}
        byte[] pixels=new byte[1024];for(int y0=0;y0<64;y0++)for(int x=0;x<128;x++)if(Color.red(image.getPixel(x,y0))>127)pixels[y0*16+x/8]|=1<<(7-x%8);
        JSONObject body=new JSONObject().put("op","hud").put("bitmap",Base64.encodeToString(pixels,Base64.NO_WRAP));image.recycle();
        if(!writer.latest(()->writeFrame(body)))listener.status("BLE 忙，HUD 待下次刷新");
    }catch(Exception e){listener.status("HUD 生成失败");}}
    public synchronized void playSpeech(byte[] pcm)throws Exception{
        if(!ready()||pcm.length<2||pcm.length>256000||pcm.length%2!=0)throw new IllegalArgumentException("需16kHz PCM16，最长8秒");
        speech=pcm;speechOffset=0;send(new JSONObject().put("op","speaker_start").put("bytes",pcm.length).put("sha256",TlsApi.hex(java.security.MessageDigest.getInstance("SHA-256").digest(pcm))));
    }
    private synchronized void speakerChunk(int offset)throws Exception{
        if(speech==null||offset!=speechOffset)return;
        if(offset==speech.length){send(new JSONObject().put("op","speaker_play"));speech=null;return;}
        int end=Math.min(speech.length,offset+384);byte[] chunk=Arrays.copyOfRange(speech,offset,end);speechOffset=end;
        send(new JSONObject().put("op","speaker_data").put("offset",offset).put("data",Base64.encodeToString(chunk,Base64.NO_WRAP)));
    }
    public void close(){writer.close();if(written!=null)written.countDown();if(gatt!=null){gatt.disconnect();gatt.close();}session=null;rx=null;}
}
