package app.vcuria.p7m_gratis;
import java.nio.file.*;
import java.io.*;
import java.security.cert.*;
import java.util.*;
public class CertificateTrustTest {
  public static void main(String[] args) throws Exception {
    Path fixtures = Path.of(args[0]);
    byte[] leaf = Files.readAllBytes(fixtures.resolve("leaf.der"));
    byte[] rootDer = Files.readAllBytes(fixtures.resolve("root.der"));
    CertificateFactory factory = CertificateFactory.getInstance("X.509");
    X509Certificate root = (X509Certificate)factory.generateCertificate(new ByteArrayInputStream(rootDer));
    X509Certificate wrong = (X509Certificate)factory.generateCertificate(new ByteArrayInputStream(Files.readAllBytes(fixtures.resolve("wrong_root.der"))));
    Set<TrustAnchor> anchors = Set.of(new TrustAnchor(root,null));
    long time = java.time.OffsetDateTime.parse(Files.readString(fixtures.resolve("validation_time.txt"))).toInstant().toEpochMilli();
    List<byte[]> embedded = List.of(leaf,rootDer);
    require(Boolean.TRUE.equals(CertificateTrust.verifyWithAnchors(leaf,embedded,time,anchors).get("trusted")), "valid PKIX path");
    require(!Boolean.TRUE.equals(CertificateTrust.verifyWithAnchors(leaf,embedded,time,Set.of(new TrustAnchor(wrong,null))).get("trusted")), "embedded root must not become trusted");
    byte[] damaged = leaf.clone(); damaged[damaged.length-1]^=1;
    require(!Boolean.TRUE.equals(CertificateTrust.verifyWithAnchors(damaged,embedded,time,anchors).get("trusted")), "invalid certificate signature");
    require(Boolean.FALSE.equals(CertificateTrust.verifyWithAnchors(leaf,embedded,time+400L*86400000,anchors).get("trusted")), "expired certificate");
    require(Boolean.FALSE.equals(CertificateTrust.verifyWithAnchors(leaf,embedded,time-400L*86400000,anchors).get("trusted")), "certificate not yet valid");
    System.out.println("5 native PKIX checks passed");
  }
  private static void require(boolean value,String message) { if(!value) throw new AssertionError(message); }
}
