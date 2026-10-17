import dev.agentglass.PcmWave;
import java.io.*;
import java.nio.*;
import java.nio.file.*;

/** Runs the actual Android app's platform-independent WAV parser on a host JVM. */
public class PcmWaveCheck {
    static byte[] wav(int rate,int channels,int frames,int format) {
        ByteBuffer b=ByteBuffer.allocate(44+frames*channels*2).order(ByteOrder.LITTLE_ENDIAN);
        b.put(new byte[]{82,73,70,70}).putInt(b.capacity()-8).put(new byte[]{87,65,86,69,102,109,116,32}).putInt(16);
        b.putShort((short)format).putShort((short)channels).putInt(rate).putInt(rate*channels*2).putShort((short)(channels*2)).putShort((short)16);
        b.put(new byte[]{100,97,116,97}).putInt(frames*channels*2);
        for(int i=0;i<frames;i++)for(int ch=0;ch<channels;ch++)b.putShort((short)(ch==0?1000:-1000));return b.array();
    }
    static void check(boolean condition,String name){if(!condition)throw new AssertionError(name);System.out.println("PASS "+name);}
    static boolean rejects(File f){try{PcmWave.read(f);return false;}catch(Exception e){return true;}}
    public static void main(String[] args)throws Exception{
        Path path=Files.createTempFile("agentglass-pcm-",".wav");File file=path.toFile();
        try{
            Files.write(path,wav(16000,1,1600,1));byte[] out=PcmWave.read(file);check(out.length==3200,"mono_length");check(ByteBuffer.wrap(out).order(ByteOrder.LITTLE_ENDIAN).getShort()==1000,"mono_values");
            Files.write(path,wav(48000,2,48000,1));out=PcmWave.read(file);check(out.length==32000,"stereo_resample_length");check(ByteBuffer.wrap(out).order(ByteOrder.LITTLE_ENDIAN).getShort()==0,"stereo_mix");
            Files.write(path,wav(16000,1,16000*12,1));check(PcmWave.read(file).length==256000,"eight_second_bound");
            Files.write(path,wav(16000,1,1600,3));check(rejects(file),"float_rejected");
            Files.write(path,new byte[]{1,2,3});check(rejects(file),"truncation_rejected");
        }finally{Files.deleteIfExists(path);}
    }
}
