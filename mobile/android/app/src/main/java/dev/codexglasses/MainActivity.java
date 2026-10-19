package dev.codexglasses;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.*;
import android.speech.RecognizerIntent;
import android.speech.tts.TextToSpeech;
import android.util.Base64;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.*;

/** Foreground engineering companion; no hidden background recording. */
public class MainActivity extends Activity implements BleLink.Listener {
    private LinearLayout layout;private EditText url,pin,code,prompt,address,key,opticAddress,opticKey;
    private Spinner projects,actions,language;private CheckBox follow;private TextView hud,log;private volatile TlsApi api;private volatile BleLink ble;
    private volatile BleLink opticalDisplay;
    private final TaskDispatch control=new TaskDispatch("control",8),polling=new TaskDispatch("poll",1),
        receiving=new TaskDispatch("media-receive",16),uploading=new TaskDispatch("media-upload",2),urgent=new TaskDispatch("cancel",1);
    private final Handler handler=new Handler(Looper.getMainLooper());
    private TextToSpeech tts;private volatile long cursor=0;private volatile String summary="";private String requestId=null;private volatile boolean active;
    private final Map<String,JSONObject> media=new HashMap<>();
    private volatile String newestTask;
    private final Object connectionLock=new Object(),pendingLock=new Object();
    private String lastNotification="";private long notificationUntil=0;
    private volatile String lastGlassHud="";
    private volatile int hudPage=0;
    private volatile String computerName="未连接电脑";
    public void onCreate(Bundle saved){super.onCreate(saved);
        ScrollView scroll=new ScrollView(this);layout=new LinearLayout(this);layout.setOrientation(LinearLayout.VERTICAL);layout.setPadding(28,28,28,36);scroll.addView(layout);setContentView(scroll);
        title("CodexGlasses / 工程预览");text("手机负责中文语音、联网和可靠存储；每个 Codex 任务须在电脑端批准。",15);
        android.content.SharedPreferences prefs=getSharedPreferences("settings",MODE_PRIVATE);
        url=edit("电脑 HTTPS 地址",prefs.getString("url","https://192.168.1.2:9443"));pin=edit("电脑显示的证书 SHA-256 指纹",prefs.getString("pin",""));
        code=edit("一次性配对码（首次绑定）","");code.setInputType(129);
        button("核对指纹并连接",()->{String endpoint=url.getText().toString().trim(),fingerprint=pin.getText().toString().trim(),pairCode=code.getText().toString().trim();work(()->{TlsApi next=new TlsApi(this,endpoint,fingerprint);
            if(!pairCode.isEmpty())next.pair(pairCode);JSONObject health=next.request("GET","/health",null);
            JSONArray p=next.request("GET","/v1/projects",null).getJSONArray("projects");ArrayList<String> ids=new ArrayList<>();for(int i=0;i<p.length();i++)ids.add(p.getJSONObject(i).getString("id"));
            getSharedPreferences("settings",MODE_PRIVATE).edit().putString("url",endpoint).putString("pin",fingerprint).apply();
            synchronized(connectionLock){computerName=health.optString("computer_name","CodexGlasses PC");api=next;cursor=0;lastGlassHud="";}
            runOnUiThread(()->{projects.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,ids));code.setText("");append("已连接 "+computerName+" / "+health.optString("mode"));requestPoll();});});});
        title("指令");projects=new Spinner(this);layout.addView(projects);actions=new Spinner(this);
        actions.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"inspect","fix","test"}));layout.addView(actions);
        prompt=edit("说出或输入完整指令","");prompt.setMinLines(2);
        follow=new CheckBox(this);follow.setText("继续最近完成任务的会话和项目副本");layout.addView(follow);
        language=new Spinner(this);language.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"中文 zh-CN","English en-US"}));layout.addView(language);
        button("语音输入（手机麦克风）",()->{try{Intent intent=new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE,language.getSelectedItemPosition()==0?"zh-CN":"en-US");intent.putExtra(RecognizerIntent.EXTRA_PROMPT,"确认识别结果后点击发送 / Review before sending");startActivityForResult(intent,41);}catch(ActivityNotFoundException e){append("本机没有语音识别服务，请输入指令");}});
        button("确认并发送任务",()->{TlsApi confirmed;String name;synchronized(connectionLock){confirmed=api;name=computerName;}if(confirmed==null){append("请先连接电脑");return;}
            new AlertDialog.Builder(this).setTitle("确认目标和指令").setMessage(name+"\n"+confirmed.origin()+"\n"+String.valueOf(projects.getSelectedItem())+" / "+actions.getSelectedItem()+"\n"+prompt.getText()).setPositiveButton("发送",(d,w)->submit(confirmed)).setNegativeButton("返回",null).show();});
        button("取消最近任务",()->dispatch(urgent,()->{if(api==null||newestTask==null)throw new IllegalStateException("没有已连接任务");api.request("POST","/v1/tasks/"+newestTask+"/cancel",new JSONObject());}));
        hud=text("HUD / 等待真实任务状态",22);hud.setTextColor(Color.rgb(150,245,183));hud.setPadding(18,22,18,22);hud.setBackgroundColor(Color.rgb(8,22,17));
        button("切换眼镜页面：状态 / 步骤 / 结果",()->{hudPage=(hudPage+1)%3;lastGlassHud="";requestPoll();});
        button("朗读最新结果（手机）",()->{if(tts!=null&&!summary.isEmpty()){tts.setLanguage(language.getSelectedItemPosition()==0?Locale.SIMPLIFIED_CHINESE:Locale.US);tts.speak(summary,TextToSpeech.QUEUE_FLUSH,null,"summary");}});
        button("在眼镜播放短语音（实验功能）",()->{
            if(tts==null||summary.isEmpty()||ble==null||!ble.ready()){append("需要已连接眼镜和可朗读结果");return;}
            String utterance="glasses_reply_"+UUID.randomUUID();File audio=new File(getCacheDir(),utterance+".wav");
            tts.setLanguage(language.getSelectedItemPosition()==0?Locale.SIMPLIFIED_CHINESE:Locale.US);
            tts.setOnUtteranceProgressListener(new android.speech.tts.UtteranceProgressListener(){
                public void onStart(String id){}public void onError(String id){if(utterance.equals(id)){audio.delete();append("语音合成失败");}}
                public void onDone(String id){if(utterance.equals(id))uploadWork(()->{try{ble.playSpeech(PcmWave.read(audio));append("短语音正在传至眼镜，校验后播放；当前BLE路径有等待时间。");}finally{audio.delete();}});}
            });
            String text=summary.substring(0,Math.min(90,summary.length()));tts.synthesizeToFile(text,new Bundle(),audio,utterance);
        });
        title("眼镜 D0 配件");text("首次在受信任 USB 上配置密钥并完成系统蓝牙绑定；本页不兼容 Halo 的专用 BLE 协议。",14);
        address=edit("蓝牙 MAC 地址（系统蓝牙设置中查看）",prefs.getString("ble_address",""));key=edit("USB 配置的 64 位十六进制密钥","");key.setInputType(129);
        button("绑定并连接眼镜",()->{try{
            if(Build.VERSION.SDK_INT>=31&&(checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT)!=PackageManager.PERMISSION_GRANTED||checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN)!=PackageManager.PERMISSION_GRANTED)){requestPermissions(new String[]{Manifest.permission.BLUETOOTH_CONNECT,Manifest.permission.BLUETOOTH_SCAN},52);return;}
            String secret=key.getText().toString().trim();if(secret.isEmpty())secret=TlsApi.readSecret(this,"glasses_key");if(secret==null)throw new IllegalStateException("请先输入眼镜密钥");
            if(ble!=null)ble.close();ble=new BleLink(this,this);ble.connect(address.getText().toString().trim(),secret);TlsApi.saveSecret(this,"glasses_key",secret);key.setText("");getSharedPreferences("settings",MODE_PRIVATE).edit().putString("ble_address",address.getText().toString().trim()).apply();
        }catch(Exception e){append(e.getMessage());}});
        button("眼镜拍照",()->glass("photo",0));button("眼镜录制 5 秒 JPEG 帧",()->glass("record",5));button("眼镜录音 3 秒 WAV",()->glass("audio",3));button("同步眼镜未传媒体",()->glass("list",0));
        button("上传本机已收媒体到电脑",()->uploadWork(this::uploadMedia));
        button("AI 转写最近眼镜录音",()->confirmAI("transcribe"));
        button("AI 询问最近眼镜照片",()->confirmAI("vision"));
        title("P1 可选近眼 HUD / T-Glass V2");
        text("独立显示配件，使用原厂完整显示器与棱镜。相机仍由 D0 控制；此组合不是 H1 整机，也没有实物光学验收。",14);
        opticAddress=edit("T-Glass V2 蓝牙 MAC",prefs.getString("tglass_address",""));opticKey=edit("T-Glass 独立 USB 配置密钥","");opticKey.setInputType(129);
        button("连接 T-Glass 近眼显示",()->{try{
            if(Build.VERSION.SDK_INT>=31&&(checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT)!=PackageManager.PERMISSION_GRANTED||checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN)!=PackageManager.PERMISSION_GRANTED)){requestPermissions(new String[]{Manifest.permission.BLUETOOTH_CONNECT,Manifest.permission.BLUETOOTH_SCAN},52);return;}
            String secret=opticKey.getText().toString().trim();if(secret.isEmpty())secret=TlsApi.readSecret(this,"tglass_key");if(secret==null)throw new IllegalStateException("请先在 T-Glass 上配置独立密钥");
            if(opticalDisplay!=null)opticalDisplay.close();
            opticalDisplay=new BleLink(this,new BleLink.Listener(){public void status(String value){append("近眼显示："+value);}public void message(JSONObject m){
                if("hello".equals(m.optString("type")))try{if(!"TGLASS_V2_NEAR_EYE".equals(m.optString("profile"))){opticalDisplay.close();throw new SecurityException("显示配件型号不匹配");}lastGlassHud="";opticalDisplay.send(new JSONObject().put("op","status").put("unix",System.currentTimeMillis()/1000).put("tz_minutes",TimeZone.getDefault().getOffset(System.currentTimeMillis())/60000));}catch(Exception e){append(e.getMessage());}
            }});
            opticalDisplay.connect(opticAddress.getText().toString().trim(),secret);TlsApi.saveSecret(this,"tglass_key",secret);opticKey.setText("");getSharedPreferences("settings",MODE_PRIVATE).edit().putString("tglass_address",opticAddress.getText().toString().trim()).apply();
        }catch(Exception e){append(e.getMessage());}});
        button("开启通知摘要（自选应用）",()->startActivity(new Intent("android.settings.ACTION_NOTIFICATION_LISTENER_SETTINGS")));
        button("选择允许通知的应用",this::chooseNotificationApps);
        text("通知默认关闭，只处理所选应用的标题。标题可能包含私人信息；不上传通知正文。",13);
        title("状态");log=text("尚未连接",13);
        tts=new TextToSpeech(this,result->{if(result==TextToSpeech.SUCCESS)tts.setLanguage(Locale.SIMPLIFIED_CHINESE);});
    }
    private void title(String value){TextView v=text(value,23);v.setPadding(0,20,0,10);}
    private TextView text(String value,int size){TextView v=new TextView(this);v.setText(value);v.setTextSize(size);layout.addView(v);return v;}
    private EditText edit(String hint,String value){EditText e=new EditText(this);e.setHint(hint);e.setText(value);e.setSingleLine(false);layout.addView(e);return e;}
    private void button(String value,Runnable r){Button b=new Button(this);b.setText(value);layout.addView(b);b.setOnClickListener(v->r.run());}
    private void append(String s){runOnUiThread(()->{if(log!=null)log.setText(s+"\n"+log.getText().toString().substring(0,Math.min(2200,log.length())));});}
    private interface Work {void run() throws Exception;}
    private void dispatch(TaskDispatch queue,Work operation){if(!queue.offer(()->{try{operation.run();}catch(Exception e){append(e.getClass().getSimpleName()+": "+e.getMessage());}}))append("操作队列已满，请稍后重试；未确认媒体仍保留在眼镜。");}
    private void work(Work operation){dispatch(control,operation);}
    private void uploadWork(Work operation){dispatch(uploading,operation);}
    private void requestPoll(){
        if(!active||api==null)return;TlsApi current=api;
        polling.once(()->{try{if(active&&api==current)poll(current);}catch(Exception e){append("连接状态："+e.getMessage());}});
    }
    private void submit(TlsApi confirmed){
        if(api!=confirmed){append("电脑连接已变更，请重新确认目标。");return;}
        if(projects.getSelectedItem()==null){append("请先连接并选择项目");return;}
        String project=projects.getSelectedItem().toString(),action=actions.getSelectedItem().toString(),input=prompt.getText().toString();
        String parent=follow.isChecked()?newestTask:null;
        String fingerprint=confirmed.identity()+"\n"+project+"\n"+action+"\n"+input+"\n"+parent;
        String id;synchronized(pendingLock){String prior=getSharedPreferences("pending",MODE_PRIVATE).getString("body","");
            id=fingerprint.equals(prior)?getSharedPreferences("pending",MODE_PRIVATE).getString("id",UUID.randomUUID().toString()):UUID.randomUUID().toString();
            if(!getSharedPreferences("pending",MODE_PRIVATE).edit().putString("body",fingerprint).putString("id",id).commit()){append("任务记录无法持久化，未发送。");return;}}
        work(()->{if(api!=confirmed)throw new IllegalStateException("电脑连接已变更，请重新确认目标");JSONObject request=new JSONObject().put("v",1).put("request_id",id).put("project",project).put("action",action).put("prompt",input);if(parent!=null)request.put("parent_task_id",parent);
            JSONObject response=confirmed.request("POST","/v1/tasks",request);
            synchronized(pendingLock){if(id.equals(getSharedPreferences("pending",MODE_PRIVATE).getString("id","")))getSharedPreferences("pending",MODE_PRIVATE).edit().clear().commit();}
            newestTask=response.getString("id");append("电脑已接收，等待本地批准："+newestTask);});
    }
    private final Runnable ticker=new Runnable(){public void run(){requestPoll();if(active)handler.postDelayed(this,1500);}};
    protected void onStart(){super.onStart();active=true;handler.removeCallbacks(ticker);handler.post(ticker);}
    protected void onStop(){active=false;handler.removeCallbacks(ticker);super.onStop();}
    protected void onDestroy(){active=false;handler.removeCallbacks(ticker);if(ble!=null)ble.close();if(opticalDisplay!=null)opticalDisplay.close();if(tts!=null)tts.shutdown();control.close();urgent.close();polling.close();receiving.close();uploading.close();super.onDestroy();}
    protected void onActivityResult(int request,int result,Intent data){super.onActivityResult(request,result,data);if(request==41&&result==RESULT_OK&&data!=null){ArrayList<String> values=data.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS);if(values!=null&&!values.isEmpty())prompt.setText(values.get(0));}}
    private String human(String status){switch(status){case "pending":return "等待电脑批准";case "preparing":return "准备项目副本";case "running":return "正在运行";case "cancel_requested":return "等待取消确认";case "completed":return "任务完成";case "failed":return "任务失败";case "unknown":return "状态未知";case "cancelled":return "已取消";case "rejected":return "已拒绝";default:return status;}}
    private void poll(TlsApi current)throws Exception{
        JSONObject events=current.request("GET","/v1/events?after="+cursor,null);if(api!=current||!active)return;JSONArray list=events.getJSONArray("events");
        for(int i=0;i<list.length();i++){JSONObject e=list.getJSONObject(i);if("summary".equals(e.optString("kind")))summary=e.getJSONObject("data").optString("text");}
        synchronized(connectionLock){if(api!=current)return;cursor=events.getLong("cursor");}JSONArray tasks=current.request("GET","/v1/tasks",null).getJSONArray("tasks");if(api!=current||!active)return;
        String header=new java.text.SimpleDateFormat("HH:mm",Locale.getDefault()).format(new Date())+" "+computerName.substring(0,Math.min(4,computerName.length()));
        String display=header+"\n已连接电脑";
        if(tasks.length()>0){JSONObject t=tasks.getJSONObject(0);newestTask=t.getString("id");summary=t.optString("last_summary","");display=header+"\n"+t.getString("project")+"\n"+(hudPage==1?t.optString("progress_text",""):hudPage==2?summary:human(t.getString("status")));}
        String notification=getSharedPreferences("settings",MODE_PRIVATE).getString("latest_notification","");
        if(!notification.isEmpty()&&!notification.equals(lastNotification)){lastNotification=notification;notificationUntil=System.currentTimeMillis()+6000;}
        if(System.currentTimeMillis()<notificationUntil)display="通知\n"+notification;
        String shown=display;runOnUiThread(()->hud.setText(shown));if(!shown.equals(lastGlassHud)){
            boolean sent=false;if(ble!=null&&ble.ready()){ble.hud(shown);sent=true;}if(opticalDisplay!=null&&opticalDisplay.ready()){opticalDisplay.hud(shown);sent=true;}if(sent)lastGlassHud=shown;
        }
    }
    private void glass(String op,int seconds){try{if(ble==null||!ble.ready())throw new IllegalStateException("请先连接眼镜");JSONObject j=new JSONObject().put("op",op);if(seconds>0)j.put("seconds",seconds);ble.send(j);}catch(Exception e){append(e.getMessage());}}
    public void status(String value){append(value);}
    public void message(JSONObject message){
        if(message.optString("type").equals("hello")&&ble!=null)try{lastGlassHud="";ble.send(new JSONObject().put("op","status").put("unix",System.currentTimeMillis()/1000).put("tz_minutes",java.util.TimeZone.getDefault().getOffset(System.currentTimeMillis())/60000));}catch(Exception e){append("校时失败");}
        dispatch(receiving,()->receiveMedia(message));
    }
    private void receiveMedia(JSONObject m)throws Exception{
        String type=m.optString("type");if("error".equals(type)){append("眼镜："+m.optString("code"));return;}
        if("media".equals(type)){
            String id=m.getString("id");if(!id.matches("(?:[0-9]{1,10}|[a-z2-7]{26})")||m.getLong("size")<1||m.getLong("size")>64*1024*1024||!m.getString("sha256").matches("[0-9a-f]{64}")||!Arrays.asList("image/jpeg","audio/wav","video/x-motion-jpeg").contains(m.getString("mime")))throw new SecurityException("invalid media metadata");
            media.put(id,m);File f=new File(getFilesDir(),"glass_"+id+".part");
            if(new File(getFilesDir(),"glass_"+id+".media").isFile()){finishMedia(id,m,f);return;}
            if(f.exists()&&f.length()>m.getLong("size"))throw new IOException("invalid partial file");
            if(f.length()==m.getLong("size")){finishMedia(id,m,f);return;}
            ble.send(new JSONObject().put("op","read").put("id",id).put("offset",f.length()));
        }else if("chunk".equals(type)){
            String id=m.getString("id");JSONObject meta=media.get(id);if(meta==null)return;
            File f=new File(getFilesDir(),"glass_"+id+".part");long offset=m.getLong("offset");byte[] data=Base64.decode(m.getString("data"),Base64.NO_WRAP);
            if(data.length>384||offset!=f.length()||offset+data.length>meta.getLong("size"))throw new IOException("media offset conflict");
            try(FileOutputStream out=new FileOutputStream(f,true)){out.write(data);out.getFD().sync();}
            if(f.length()==meta.getLong("size"))finishMedia(id,meta,f);else ble.send(new JSONObject().put("op","read").put("id",id).put("offset",f.length()));
        }
    }
    private void finishMedia(String id,JSONObject meta,File partial)throws Exception{
        File target=new File(getFilesDir(),"glass_"+id+".media"),source=target.isFile()?target:partial;
        if(source.length()!=meta.getLong("size"))throw new SecurityException("本地媒体长度冲突，保留眼镜原件");
        MessageDigest digest=MessageDigest.getInstance("SHA-256");try(InputStream in=new FileInputStream(source)){byte[] buffer=new byte[4096];int n;while((n=in.read(buffer))!=-1)digest.update(buffer,0,n);}
        if(!TlsApi.hex(digest.digest()).equals(meta.getString("sha256")))throw new SecurityException("媒体 SHA-256 不匹配，保留眼镜原件");
        if(!source.equals(target)&&!partial.renameTo(target))throw new IOException("media rename failed");
        File manifest=new File(target.getPath()+".json");JSONObject stored=readManifest(manifest);
        if(stored!=null){if(!stored.getString("sha256").equals(meta.getString("sha256")))throw new SecurityException("媒体 ID 冲突");meta=stored;}
        else {meta.put("received_at",System.currentTimeMillis());saveManifest(manifest,meta);}
        syncDirectory(getFilesDir());
        media.remove(id);ble.send(new JSONObject().put("op","ack").put("id",id).put("sha256",meta.getString("sha256")));append("照片/录制已核验并保存到手机："+id);
    }
    private void syncDirectory(File folder)throws IOException{
        try{
        java.io.FileDescriptor directory=android.system.Os.open(folder.getPath(),android.system.OsConstants.O_RDONLY,0);
        try{android.system.Os.fsync(directory);}finally{android.system.Os.close(directory);}
        }catch(android.system.ErrnoException e){throw new IOException("目录持久化失败",e);}
    }
    private JSONObject readManifest(File file)throws Exception{
        boolean valid=DurableFiles.recover(file,bytes->{try{JSONObject j=new JSONObject(new String(bytes,java.nio.charset.StandardCharsets.UTF_8));return j.has("id")&&j.has("size")&&j.optString("sha256").matches("[0-9a-f]{64}");}catch(Exception e){return false;}},this::syncDirectory);
        if(!valid){if(file.exists()||new File(file.getPath()+".new").exists())throw new IOException("媒体记录损坏，保留媒体并跳过："+file.getName());return null;}
        return new JSONObject(new String(java.nio.file.Files.readAllBytes(file.toPath()),java.nio.charset.StandardCharsets.UTF_8));
    }
    private void saveManifest(File file,JSONObject meta)throws Exception{
        DurableFiles.write(file,meta.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8),this::syncDirectory);
    }
    private void uploadMedia()throws Exception{
        TlsApi current=api;if(current==null)throw new IllegalStateException("请先连接电脑");File[] files=getFilesDir().listFiles((d,n)->n.endsWith(".media.json")||n.endsWith(".media.json.new"));if(files==null)return;
        Set<String> handled=new HashSet<>();
        for(File entry:files){File manifest=entry.getName().endsWith(".new")?new File(entry.getPath().substring(0,entry.getPath().length()-4)):entry;if(!handled.add(manifest.getPath()))continue;
          try{JSONObject m=readManifest(manifest);if(m==null)continue;
            if(m.optBoolean("desktop_complete")&&current.identity().equals(m.optString("desktop_pin")))continue;
            if(!m.has("upload_request_id"))m.put("upload_request_id",UUID.randomUUID().toString());
            if(!m.has("received_at"))m.put("received_at",manifest.lastModified());
            m.put("desktop_pin",current.identity());saveManifest(manifest,m);
            // Always retry the same initiation key, including after a lost POST reply.
            String upload=current.request("POST","/v1/media",new JSONObject().put("request_id",m.getString("upload_request_id")).put("size",m.getLong("size")).put("sha256",m.getString("sha256")).put("mime",m.getString("mime"))).getString("id");
            m.put("desktop_id",upload);saveManifest(manifest,m);
            JSONObject state=current.request("GET","/v1/media/"+upload,null);long offset=state.getLong("received");File content=new File(manifest.getPath().substring(0,manifest.getPath().length()-5));
            if(offset<0||offset>m.getLong("size")||content.length()!=m.getLong("size"))throw new IOException("媒体长度/恢复偏移无效");
            if(!state.optBoolean("complete"))try(RandomAccessFile in=new RandomAccessFile(content,"r")){in.seek(offset);byte[] chunk=new byte[65536];int n;while((n=in.read(chunk))!=-1){byte[] block=Arrays.copyOf(chunk,n);long next=current.raw("PUT","/v1/media/"+upload+"/chunks?offset="+offset,block,"application/octet-stream").getLong("offset");if(next!=offset+n)throw new IOException("上传偏移确认不匹配");offset=next;}}
            current.request("POST","/v1/media/"+upload+"/commit",new JSONObject());m.put("desktop_complete",true);saveManifest(manifest,m);append("电脑已核验保存："+m.getString("id"));
          }catch(Exception e){append("上传保留待重试 "+manifest.getName()+"："+e.getMessage());}
        }
    }
    private void chooseNotificationApps(){
        Intent intent=new Intent(Intent.ACTION_MAIN);intent.addCategory(Intent.CATEGORY_LAUNCHER);
        java.util.List<android.content.pm.ResolveInfo> apps=getPackageManager().queryIntentActivities(intent,0);
        java.util.LinkedHashMap<String,String> unique=new java.util.LinkedHashMap<>();for(android.content.pm.ResolveInfo app:apps)unique.put(app.activityInfo.packageName,app.loadLabel(getPackageManager()).toString());
        String[] packages=unique.keySet().toArray(new String[0]),labels=unique.values().toArray(new String[0]);boolean[] checked=new boolean[packages.length];
        java.util.Set<String> selected=new java.util.HashSet<>(getSharedPreferences("settings",MODE_PRIVATE).getStringSet("notification_packages",java.util.Collections.emptySet()));
        for(int i=0;i<packages.length;i++)checked[i]=selected.contains(packages[i]);
        new AlertDialog.Builder(this).setTitle("只转发所选应用标题").setMultiChoiceItems(labels,checked,(d,w,on)->{if(on)selected.add(packages[w]);else selected.remove(packages[w]);}).setPositiveButton("保存",(d,w)->getSharedPreferences("settings",MODE_PRIVATE).edit().putStringSet("notification_packages",selected).apply()).setNegativeButton("取消",null).show();
    }
    private void confirmAI(String kind){
        EditText question=new EditText(this);question.setText("这张图片里有什么？请简短回答。");
        AlertDialog.Builder dialog=new AlertDialog.Builder(this).setTitle(kind.equals("vision")?"询问最近照片":"转写最近录音");
        if(kind.equals("vision"))dialog.setView(question);
        dialog.setMessage("将选定媒体提交到 OpenAI API，可能产生费用。电脑须事先开启云服务；转写结果不会自动执行任务。");
        dialog.setPositiveButton("同意并提交",(d,w)->{String questionText=question.getText().toString();uploadWork(()->{
            uploadMedia();File[] files=getFilesDir().listFiles((dir,n)->n.endsWith(".media.json"));File selected=null;JSONObject meta=null;
            if(files!=null)for(File file:files){try{JSONObject candidate=readManifest(file);if(candidate!=null&&candidate.optBoolean("desktop_complete")&&api.identity().equals(candidate.optString("desktop_pin"))&&candidate.optString("mime").equals(kind.equals("vision")?"image/jpeg":"audio/wav")&&(selected==null||candidate.optLong("received_at",0)>meta.optLong("received_at",0))){selected=file;meta=candidate;}}catch(Exception e){append(e.getMessage());}}
            if(meta==null)throw new IllegalStateException("没有匹配的已收媒体");
            JSONObject result=api.request("POST","/v1/ai",new JSONObject().put("kind",kind).put("media_id",meta.getString("desktop_id")).put("question",questionText).put("consent_upload_and_cost",true));
            summary=result.getString("text");String text=summary;runOnUiThread(()->{hud.setText(text);if(kind.equals("transcribe"))prompt.setText(text);});if(ble!=null&&ble.ready())ble.hud(text);if(opticalDisplay!=null&&opticalDisplay.ready())opticalDisplay.hud(text);append("AI 已返回；可朗读或核对后发送任务。");
        });}).setNegativeButton("取消",null).show();
    }
}
