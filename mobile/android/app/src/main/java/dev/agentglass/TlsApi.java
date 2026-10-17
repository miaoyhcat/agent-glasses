package dev.agentglass;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import org.json.JSONObject;
import javax.net.ssl.*;
import javax.crypto.*;
import javax.crypto.spec.GCMParameterSpec;
import java.security.*;
import java.security.cert.X509Certificate;
import java.net.URL;
import java.io.*;
import java.nio.charset.StandardCharsets;

/** Certificate pinning is explicit trust; there is no trust-all fallback. */
public final class TlsApi {
    private final Context context;
    private final String base, pin;
    private volatile String token;
    public String identity(){return pin;}
    public String origin(){return base;}
    public TlsApi(Context c,String base,String fingerprint) throws Exception {
        this.context=c;this.base=base.replaceAll("/+$", "");
        URL u=new URL(this.base);
        if(!"https".equals(u.getProtocol()) || u.getUserInfo()!=null || !u.getPath().isEmpty() || u.getQuery()!=null || u.getRef()!=null)throw new SecurityException("仅允许 HTTPS 主机和端口");
        pin=fingerprint.replace(":", "").toLowerCase(java.util.Locale.ROOT);
        if(!pin.matches("[0-9a-f]{64}"))throw new SecurityException("需要完整的 SHA-256 证书指纹");
        token=readSecret(c,"device_token_"+pin);
    }
    public static String hex(byte[] bytes){StringBuilder s=new StringBuilder();for(byte b:bytes)s.append(String.format(java.util.Locale.ROOT,"%02x",b&255));return s.toString();}
    private SSLContext tls() throws Exception {
        TrustManager[] managers={new X509TrustManager(){
            public X509Certificate[] getAcceptedIssuers(){return new X509Certificate[0];}
            public void checkClientTrusted(X509Certificate[] chain,String type)throws java.security.cert.CertificateException{throw new java.security.cert.CertificateException("client trust unsupported");}
            public void checkServerTrusted(X509Certificate[] chain,String type)throws java.security.cert.CertificateException{
                try{if(chain==null||chain.length==0)throw new SecurityException();chain[0].checkValidity();
                    String actual=hex(MessageDigest.getInstance("SHA-256").digest(chain[0].getEncoded()));
                    if(!MessageDigest.isEqual(pin.getBytes(StandardCharsets.US_ASCII),actual.getBytes(StandardCharsets.US_ASCII)))throw new SecurityException();
                }catch(Exception e){throw new java.security.cert.CertificateException("证书指纹不匹配",e);}
            }
        }};
        SSLContext ctx=SSLContext.getInstance("TLS");ctx.init(null,managers,new SecureRandom());return ctx;
    }
    public void pair(String code) throws Exception {
        JSONObject response=request("POST","/v1/pair",new JSONObject().put("code",code).put("name","AgentGlass Android"));
        token=response.getString("token");saveSecret(context,"device_token_"+pin,token);
    }
    public JSONObject request(String method,String path,JSONObject data) throws Exception {
        return raw(method,path,data==null?null:data.toString().getBytes(StandardCharsets.UTF_8),"application/json");
    }
    public JSONObject raw(String method,String path,byte[] data,String mime) throws Exception {
        if(!path.startsWith("/")||path.startsWith("//")||path.contains("\r")||path.contains("\n"))throw new SecurityException("bad path");
        HttpsURLConnection c=(HttpsURLConnection)new URL(base+path).openConnection();
        c.setSSLSocketFactory(tls().getSocketFactory());
        // Keep Android's default hostname/SAN verifier. Pinning does not disable hostname checks.
        c.setInstanceFollowRedirects(false);c.setRequestMethod(method);c.setConnectTimeout(10000);c.setReadTimeout(20000);
        if(token!=null)c.setRequestProperty("Authorization","Bearer "+token);
        c.setRequestProperty("Content-Type",mime);
        try{
            if(data!=null){c.setDoOutput(true);c.setFixedLengthStreamingMode(data.length);try(OutputStream out=c.getOutputStream()){out.write(data);}}
            int code=c.getResponseCode();InputStream in=code<400?c.getInputStream():c.getErrorStream();
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();
            if(in!=null)try(InputStream stream=in){byte[] buffer=new byte[4096];int n;while((n=stream.read(buffer))!=-1){if(bytes.size()+n>2*1024*1024)throw new IOException("response too large");bytes.write(buffer,0,n);}}
            JSONObject response=new JSONObject(new String(bytes.toByteArray(),StandardCharsets.UTF_8));
            if(code>=300)throw new IOException("HTTP "+code+" "+response.optString("error","request failed"));return response;
        }finally{c.disconnect();}
    }
    private static SecretKey secretKey() throws Exception {
        KeyStore ks=KeyStore.getInstance("AndroidKeyStore");ks.load(null);
        if(!ks.containsAlias("agentglass_v1")){
            KeyGenerator kg=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");
            kg.init(new KeyGenParameterSpec.Builder("agentglass_v1",KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());kg.generateKey();
        }
        return ((KeyStore.SecretKeyEntry)ks.getEntry("agentglass_v1",null)).getSecretKey();
    }
    public static void saveSecret(Context c,String name,String value)throws Exception{
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.ENCRYPT_MODE,secretKey());
        String encrypted=Base64.encodeToString(cipher.getIV(),Base64.NO_WRAP)+":"+Base64.encodeToString(cipher.doFinal(value.getBytes(StandardCharsets.UTF_8)),Base64.NO_WRAP);
        if(!c.getSharedPreferences("vault",Context.MODE_PRIVATE).edit().putString(name,encrypted).commit())throw new IOException("secret persistence failed");
    }
    public static String readSecret(Context c,String name)throws Exception{
        String value=c.getSharedPreferences("vault",Context.MODE_PRIVATE).getString(name,null);if(value==null)return null;
        String[] parts=value.split(":");if(parts.length!=2)throw new SecurityException("invalid vault");
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.DECRYPT_MODE,secretKey(),new GCMParameterSpec(128,Base64.decode(parts[0],Base64.NO_WRAP)));
        return new String(cipher.doFinal(Base64.decode(parts[1],Base64.NO_WRAP)),StandardCharsets.UTF_8);
    }
}
