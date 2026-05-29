import Foundation
import Testing
@testable import TGRV

@MainActor
struct TelemetryConfigurationTests {
    @Test func simulatorDefaultHostUsesLoopback() async throws {
        #if targetEnvironment(simulator)
        #expect(TelemetryConfiguration.initialHost(storedHost: nil) == "127.0.0.1")
        #else
        #expect(TelemetryConfiguration.initialHost(storedHost: nil).isEmpty)
        #endif
    }

    @Test func malformedHostIsPreservedWithoutCrash() async throws {
        let configuration = TelemetryConfiguration(host: "bad host name", port: 8765)
        #expect(configuration.host == "bad host name")
        #expect(configuration.port == 8765)
    }

    @Test func malformedHostDoesNotCrashClientConfiguration() async throws {
        LiveTelemetryClient.shared.disconnect()
        try await Task.sleep(nanoseconds: 100_000_000)
        LiveTelemetryClient.shared.updateConfiguration(host: "bad host name", port: 8765, connect: false)
        try await Task.sleep(nanoseconds: 200_000_000)

        let snapshot = LiveTelemetryClient.shared.snapshot()
        #expect(snapshot.host == "bad host name")
        #expect(snapshot.port == 8765)
        #expect(snapshot.connectionState != .connected)
    }

    @Test func connectionRefusedMessageIsActionable() async throws {
        let error = NSError(domain: NSPOSIXErrorDomain, code: 61)
        let message = TelemetryConfiguration.diagnosticMessage(for: error, host: "192.168.1.10", port: 8765)
        #expect(message.contains("Connection refused"))
        #expect(message.contains("0.0.0.0"))
        #expect(message.contains("192.168.1.10"))
    }
}
