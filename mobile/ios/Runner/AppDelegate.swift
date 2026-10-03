import Flutter
import UIKit
import Security

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  private var files: FlutterMethodChannel?
  private var pendingFile: [String: Any]?
  private var pendingError: String?
  private var ready = false
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    files = FlutterMethodChannel(name: "app.vcuria.p7m/files", binaryMessenger: engineBridge.applicationRegistrar.messenger())
    files?.setMethodCallHandler { [weak self] call, result in
      guard let self = self else { return }
      if call.method == "initialFile" {
        self.ready = true
        result(self.pendingFile)
        self.pendingFile = nil
        if let error = self.pendingError {
          self.pendingError = nil
          self.files?.invokeMethod("fileError", arguments: error)
        }
      } else if call.method == "cleanTemporaryFiles" {
        DispatchQueue.global(qos: .userInitiated).async {
          do {
            let temporary = URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true).resolvingSymlinksInPath().standardizedFileURL
            let home = URL(fileURLWithPath: NSHomeDirectory(), isDirectory: true).resolvingSymlinksInPath().standardizedFileURL
            guard temporary.path.hasPrefix(home.path + "/"), temporary.path != home.path else {
              throw NSError(domain: "P7M", code: 3)
            }
            let entries = try FileManager.default.contentsOfDirectory(at: temporary, includingPropertiesForKeys: nil)
            var failed = false
            for entry in entries {
              do { try FileManager.default.removeItem(at: entry) }
              catch { failed = true }
            }
            if failed { throw NSError(domain: "P7M", code: 4) }
            DispatchQueue.main.async { result(nil) }
          } catch {
            DispatchQueue.main.async { result(FlutterError(code: "CLEAN", message: "Pulizia temporanei incompleta", details: nil)) }
          }
        }
      } else if call.method == "verifyTrust", let args = call.arguments as? [String: Any],
                let leaf = args["leaf"] as? FlutterStandardTypedData,
                let embedded = args["certificates"] as? [FlutterStandardTypedData] {
        let time = (args["time"] as? NSNumber)?.doubleValue ?? Date().timeIntervalSince1970 * 1000
        DispatchQueue.global(qos: .userInitiated).async {
          let answer = self.verifyTrust(leaf.data, embedded.map { $0.data }, Date(timeIntervalSince1970: time / 1000))
          DispatchQueue.main.async { result(answer) }
        }
      } else { result(FlutterMethodNotImplemented) }
    }
  }

  func receiveDocument(_ url: URL) {
    guard url.isFileURL else { return }
    DispatchQueue.global(qos: .userInitiated).async {
      let scoped = url.startAccessingSecurityScopedResource()
      defer { if scoped { url.stopAccessingSecurityScopedResource() } }
      do {
        guard let input = InputStream(url: url) else { throw NSError(domain: "P7M", code: 1) }
        input.open()
        defer { input.close() }
        var buffer = [UInt8](repeating: 0, count: 65536)
        var data = Data()
        while true {
          let count = input.read(&buffer, maxLength: buffer.count)
          if count == 0 { break }
          if count < 0 || data.count + count > 50 * 1024 * 1024 { throw NSError(domain: "P7M", code: 2) }
          data.append(buffer, count: count)
        }
        let document: [String: Any] = ["name": url.lastPathComponent, "bytes": FlutterStandardTypedData(bytes: data)]
        DispatchQueue.main.async {
          if self.ready { self.files?.invokeMethod("openFile", arguments: document) }
          else { self.pendingFile = document }
          self.pendingError = nil
        }
      } catch {
        DispatchQueue.main.async {
          let error = "Impossibile leggere il documento. Limite: 50 MB."
          if self.ready { self.files?.invokeMethod("fileError", arguments: error) }
          else { self.pendingFile = nil; self.pendingError = error }
        }
      }
    }
  }

  private func verifyTrust(_ leaf: Data, _ embedded: [Data], _ date: Date) -> [String: Any] {
    guard embedded.count <= 100, let signer = SecCertificateCreateWithData(nil, leaf as CFData) else {
      return ["trusted": NSNull(), "detail": "Certificato non leggibile", "chain": []]
    }
    let certificates = [signer] + embedded.compactMap { SecCertificateCreateWithData(nil, $0 as CFData) }
    var trust: SecTrust?
    guard SecTrustCreateWithCertificates(certificates as CFArray, SecPolicyCreateBasicX509(), &trust) == errSecSuccess,
          let trust = trust else {
      return ["trusted": NSNull(), "detail": "Validazione non disponibile", "chain": []]
    }
    SecTrustSetNetworkFetchAllowed(trust, false)
    SecTrustSetVerifyDate(trust, date as CFDate)
    var error: CFError?
    let ok = SecTrustEvaluateWithError(trust, &error)
    let chain = (SecTrustCopyCertificateChain(trust) as? [SecCertificate] ?? []).map {
      FlutterStandardTypedData(bytes: SecCertificateCopyData($0) as Data)
    }
    return ["trusted": ok, "detail": ok ? "Catena verificata con le radici del dispositivo" : "Catena non attendibile, incompleta o certificato non valido", "chain": ok ? chain : []]
  }
}
