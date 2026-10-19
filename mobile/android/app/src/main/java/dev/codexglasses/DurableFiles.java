package dev.codexglasses;

import java.io.*;
import java.nio.file.*;

/** Same-directory atomic replacement. No truncate-in-place metadata updates. */
public final class DurableFiles {
    public interface DirectorySync {void sync(File directory)throws IOException;}
    public interface Validator {boolean valid(byte[] value);}
    private DurableFiles(){}
    public static synchronized void write(File target,byte[] value,DirectorySync sync)throws IOException{
        File temporary=new File(target.getPath()+".new");
        try(FileOutputStream out=new FileOutputStream(temporary)){out.write(value);out.getFD().sync();}
        // Fail closed when the filesystem cannot provide an atomic replacement.
        Files.move(temporary.toPath(),target.toPath(),StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);
        sync.sync(target.getParentFile());
    }
    public static synchronized boolean recover(File target,Validator validator,DirectorySync sync)throws IOException{
        File pending=new File(target.getPath()+".new");
        if(target.isFile()&&validator.valid(Files.readAllBytes(target.toPath())))return true;
        if(pending.isFile()&&validator.valid(Files.readAllBytes(pending.toPath()))){
            Files.move(pending.toPath(),target.toPath(),StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);
            sync.sync(target.getParentFile());return true;
        }
        return false; // Caller retains media; never acknowledge deletion on failure.
    }
}
