package dev.agentglass;
import java.io.*;
import java.nio.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

/** Strict PCM16 RIFF reader and bounded mono 16kHz conversion for short TTS. */
public final class PcmWave {
    public static byte[] read(File file) throws Exception {
        byte[] bytes=Files.readAllBytes(file.toPath());if(bytes.length<44||bytes.length>8*1024*1024)throw new IOException("Invalid WAV size");
        ByteBuffer b=ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN);
        if(!new String(bytes,0,4,StandardCharsets.US_ASCII).equals("RIFF")||!new String(bytes,8,4,StandardCharsets.US_ASCII).equals("WAVE"))throw new IOException("PCM WAV required");
        int format=0,channels=0,rate=0,bits=0,start=-1,length=0;
        for(int pos=12;pos+8<=bytes.length;){String name=new String(bytes,pos,4,StandardCharsets.US_ASCII);int n=b.getInt(pos+4);if(n<0||pos+8L+n>bytes.length)throw new IOException("Truncated WAV");
            if(name.equals("fmt ")&&n>=16){format=b.getShort(pos+8)&65535;channels=b.getShort(pos+10)&65535;rate=b.getInt(pos+12);bits=b.getShort(pos+22)&65535;}
            if(name.equals("data")){start=pos+8;length=n;}pos+=8+n+(n&1);
        }
        if(format!=1||bits!=16||channels<1||channels>2||rate<8000||rate>96000||start<0||length%(channels*2)!=0)throw new IOException("Only mono/stereo PCM16 WAV supported");
        int sourceFrames=length/(channels*2),frames=Math.min(128000,(int)((long)sourceFrames*16000/rate));if(frames<1)throw new IOException("Empty audio");
        ByteBuffer out=ByteBuffer.allocate(frames*2).order(ByteOrder.LITTLE_ENDIAN);
        for(int i=0;i<frames;i++){int index=(int)((long)i*rate/16000),sum=0;for(int ch=0;ch<channels;ch++)sum+=b.getShort(start+(index*channels+ch)*2);out.putShort((short)(sum/channels));}
        return out.array();
    }
}
