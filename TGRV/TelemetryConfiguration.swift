import Foundation
import Network

struct TelemetryConfiguration: Equatable {
    static let hostDefaultsKey = "TouchprintTelemetryHost"
    static let portDefaultsKey = "TouchprintTelemetryPort"

    var host: String
    var port: UInt16

    static func load() -> TelemetryConfiguration {
        let defaults = UserDefaults.standard
        let storedHost = defaults.string(forKey: hostDefaultsKey)
        let storedPort = UInt16(defaults.integer(forKey: portDefaultsKey))
        return TelemetryConfiguration(
            host: Self.initialHost(storedHost: storedHost),
            port: storedPort == 0 ? 8765 : storedPort
        )
    }

    func save() {
        let defaults = UserDefaults.standard
        defaults.set(host, forKey: Self.hostDefaultsKey)
        defaults.set(Int(port), forKey: Self.portDefaultsKey)
    }

    var targetDescription: String {
        let hostDescription = host.isEmpty ? "unset" : host
        return "\(hostDescription):\(port)"
    }

    var isLoopbackHost: Bool {
        host == "127.0.0.1" || host == "::1" || host == "localhost"
    }

    var deviceWarning: String? {
        #if targetEnvironment(simulator)
        return nil
        #else
        if host.isEmpty || isLoopbackHost {
            return "Use the Mac LAN IP address, not 127.0.0.1."
        }
        return nil
        #endif
    }

    var shouldAutoConnect: Bool {
        !host.isEmpty
    }

    static func initialHost(storedHost: String?) -> String {
        if let storedHost, !storedHost.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return storedHost.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        #if targetEnvironment(simulator)
        return "127.0.0.1"
        #else
        return ""
        #endif
    }

    static func diagnosticMessage(for error: Error, host: String, port: UInt16) -> String {
        if let nwError = error as? NWError {
            switch nwError {
            case .posix(.ECONNREFUSED):
                return "Connection refused: Analyzer server not reachable at \(host):\(port). Check that the Python server is running, listening on 0.0.0.0, and that host is the Mac LAN IP."
            default:
                return nwError.localizedDescription
            }
        }

        let nsError = error as NSError
        if nsError.domain == NSPOSIXErrorDomain, nsError.code == 61 {
            return "Connection refused: Analyzer server not reachable at \(host):\(port). Check that the Python server is running, listening on 0.0.0.0, and that host is the Mac LAN IP."
        }
        return error.localizedDescription
    }
}

