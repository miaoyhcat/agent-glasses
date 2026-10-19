import dev.codexglasses.DurableFiles;
import dev.codexglasses.TaskDispatch;
import java.io.*;
import java.nio.file.*;
import java.nio.channels.FileChannel;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

/** Fault injection against the same classes shipped inside the Android APK. */
public class ReliabilityCheck {
    static void check(boolean condition,String name){if(!condition)throw new AssertionError(name);System.out.println("PASS "+name);}
    static void await(CountDownLatch l){try{if(!l.await(4,TimeUnit.SECONDS))throw new AssertionError("latch timeout");}catch(InterruptedException e){Thread.currentThread().interrupt();}}
    static void sync(File folder)throws IOException{try(FileChannel c=FileChannel.open(folder.toPath(),StandardOpenOption.READ)){c.force(true);}}
    static byte[] bytes(String s)throws Exception{return s.getBytes("UTF-8");}
    static String read(File f)throws Exception{return new String(Files.readAllBytes(f.toPath()),"UTF-8");}
    public static void main(String[] args)throws Exception{
        try(TaskDispatch poll=new TaskDispatch("test-poll",1);TaskDispatch control=new TaskDispatch("test-control",2)){
            CountDownLatch started=new CountDownLatch(1),release=new CountDownLatch(1),done=new CountDownLatch(1),cancel=new CountDownLatch(1);AtomicInteger count=new AtomicInteger();
            check(poll.once(()->{count.incrementAndGet();started.countDown();await(release);done.countDown();}),"poll_started");await(started);
            for(int i=0;i<10000;i++)if(poll.once(count::incrementAndGet))throw new AssertionError("queued a duplicate poll");
            check(poll.queued()==0,"ten_thousand_slow_poll_ticks_no_backlog");
            check(control.offer(cancel::countDown),"cancel_accepted_during_blocked_poll");await(cancel);
            check(count.get()==1,"only_one_poll_in_flight");release.countDown();await(done);
        }
        try(TaskDispatch q=new TaskDispatch("bounded",2)){
            CountDownLatch started=new CountDownLatch(1),release=new CountDownLatch(1),done=new CountDownLatch(2);
            q.offer(()->{started.countDown();await(release);});await(started);
            check(q.offer(done::countDown)&&q.offer(done::countDown)&&!q.offer(()->{}),"bounded_queue_rejects_excess_work");release.countDown();await(done);
        }
        try(TaskDispatch q=new TaskDispatch("hud",2)){
            CountDownLatch started=new CountDownLatch(1),release=new CountDownLatch(1),done=new CountDownLatch(1);AtomicInteger rendered=new AtomicInteger(-1),count=new AtomicInteger();
            q.offer(()->{started.countDown();await(release);});await(started);
            for(int i=0;i<10000;i++){final int n=i;checkSilent(q.latest(()->{rendered.set(n);count.incrementAndGet();done.countDown();}));}
            check(q.queued()==1,"ten_thousand_hud_updates_coalesced");release.countDown();await(done);
            check(rendered.get()==9999&&count.get()==1,"latest_hud_is_rendered");
        }
        Path dir=Files.createTempDirectory("codexglasses-atomic-");File f=dir.resolve("manifest.json").toFile(),pending=new File(f.getPath()+".new");
        DurableFiles.Validator valid=b->new String(b,java.nio.charset.StandardCharsets.UTF_8).matches("\\{[A-Z]+\\}");
        try{
            DurableFiles.write(f,bytes("{OLD}"),ReliabilityCheck::sync);check(read(f).equals("{OLD}"),"initial_manifest_synced");
            Files.write(pending.toPath(),bytes("{TRUNCATED"));check(DurableFiles.recover(f,valid,ReliabilityCheck::sync)&&read(f).equals("{OLD}"),"interrupted_temp_write_keeps_committed_manifest");
            Files.write(f.toPath(),bytes("broken"));Files.write(pending.toPath(),bytes("{RECOVERED}"));
            check(DurableFiles.recover(f,valid,ReliabilityCheck::sync)&&read(f).equals("{RECOVERED}"),"valid_pending_recovers_broken_manifest");
            try{DurableFiles.write(f,bytes("{NEW}"),folder->{throw new IOException("injected directory sync failure");});throw new AssertionError("failure not propagated");}catch(IOException expected){}
            check(read(f).equals("{NEW}"),"post_rename_failure_keeps_whole_new_value");
            AtomicBoolean stop=new AtomicBoolean();AtomicReference<Throwable> failure=new AtomicReference<>();
            Thread reader=new Thread(()->{while(!stop.get())try{if(!valid.valid(Files.readAllBytes(f.toPath())))throw new AssertionError("torn read");}catch(Throwable e){failure.set(e);break;}});reader.start();
            for(int i=0;i<100;i++)DurableFiles.write(f,bytes(i%2==0?"{FIRST}":"{SECOND}"),ReliabilityCheck::sync);
            stop.set(true);reader.join();check(failure.get()==null,"concurrent_readers_never_see_torn_metadata");
            Files.write(f.toPath(),bytes("bad"));Files.write(pending.toPath(),bytes("also bad"));
            check(!DurableFiles.recover(f,valid,ReliabilityCheck::sync)&&f.exists()&&pending.exists(),"unrecoverable_metadata_retained_and_rejected");
        }finally{Files.deleteIfExists(pending.toPath());Files.deleteIfExists(f.toPath());Files.deleteIfExists(dir);}
    }
    static void checkSilent(boolean condition){if(!condition)throw new AssertionError("latest rejected");}
}
