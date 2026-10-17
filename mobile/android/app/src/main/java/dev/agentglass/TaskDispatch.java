package dev.agentglass;

import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

/** Bounded work and zero queued polls. Android-free so the actual code is tested. */
public final class TaskDispatch implements AutoCloseable {
    private final ThreadPoolExecutor executor;
    private final AtomicBoolean flight=new AtomicBoolean();
    private Runnable latestWork;private boolean latestScheduled;
    public TaskDispatch(String name,int capacity){
        if(capacity<1)throw new IllegalArgumentException("capacity");
        executor=new ThreadPoolExecutor(1,1,0,TimeUnit.MILLISECONDS,new ArrayBlockingQueue<Runnable>(capacity),r->{Thread t=new Thread(r,name);t.setDaemon(true);return t;},new ThreadPoolExecutor.AbortPolicy());
    }
    public boolean offer(Runnable work){try{executor.execute(work);return true;}catch(RejectedExecutionException e){return false;}}
    public boolean once(Runnable work){
        if(!flight.compareAndSet(false,true))return false;
        if(!offer(()->{try{work.run();}finally{flight.set(false);}})){flight.set(false);return false;}
        return true;
    }
    public int queued(){return executor.getQueue().size();}
    public synchronized boolean latest(Runnable work){
        latestWork=work;if(latestScheduled)return true;latestScheduled=true;
        if(offer(this::drainLatest))return true;
        latestScheduled=false;latestWork=null;return false;
    }
    private void drainLatest(){
        while(true){Runnable next;synchronized(this){next=latestWork;latestWork=null;if(next==null){latestScheduled=false;return;}}
            try{next.run();}catch(RuntimeException e){synchronized(this){latestScheduled=false;}throw e;}
        }
    }
    public synchronized void clearQueued(){executor.getQueue().clear();latestWork=null;latestScheduled=false;}
    public void close(){executor.shutdownNow();}
}
