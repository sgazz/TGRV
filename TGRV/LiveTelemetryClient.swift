import Foundation
import Network

enum LiveTelemetryConnectionState: String {
    case disconnected
    case connecting
    case connected
    case waiting
    case reconnecting
    case failed
}

enum TelemetryConnectionTestStatus: String {
    case success
    case refused
    case timeout
    case noRoute
    case permissionLikelyDenied
    case invalidHost
    case failed
}

struct TelemetryConnectionTestResult {
    let status: TelemetryConnectionTestStatus
    let message: String
    let suggestion: String
}

struct LiveTelemetrySnapshot {
    let connectionState: LiveTelemetryConnectionState
    let host: String
    let port: UInt16
    let currentSessionId: String?
    let eventsSent: Int
    let bufferedMessages: Int
    let droppedMessages: Int
    let lastError: String?
}

final class LiveTelemetryClient {
    static let shared = LiveTelemetryClient()

    private let queue = DispatchQueue(label: "com.gazza.tgrv.live-telemetry", qos: .utility)
    private var connection: NWConnection?
    private var reconnectWorkItem: DispatchWorkItem?
    private var pendingMessages: [Data]
    private let bufferLimit = 256
    private var autoReconnectEnabled = false

    private(set) var connectionState: LiveTelemetryConnectionState = .disconnected
    private(set) var eventsSent = 0
    private(set) var droppedMessages = 0
    private(set) var lastError: String?
    private(set) var currentSessionId: String?

    private var configuration: TelemetryConfiguration

    private init() {
        self.configuration = TelemetryConfiguration.load()
        self.pendingMessages = []
        self.pendingMessages.reserveCapacity(64)
    }

    func connect() {
        queue.async {
            self.autoReconnectEnabled = true
            self.connection?.cancel()
            self.connection = nil
            self.connectLocked()
        }
    }

    func disconnect() {
        queue.async {
            self.autoReconnectEnabled = false
            self.reconnectWorkItem?.cancel()
            self.reconnectWorkItem = nil
            self.connection?.cancel()
            self.connection = nil
            self.connectionState = .disconnected
        }
    }

    func updateConfiguration(host: String, port: UInt16, connect: Bool) {
        queue.async {
            self.configuration = TelemetryConfiguration(host: host.trimmingCharacters(in: .whitespacesAndNewlines), port: port == 0 ? 8765 : port)
            self.configuration.save()
            if connect {
                self.autoReconnectEnabled = true
                self.reconnectWorkItem?.cancel()
                self.reconnectWorkItem = nil
                self.connection?.cancel()
                self.connection = nil
                self.connectionState = .disconnected
                self.connectLocked()
            }
        }
    }

    func currentConfiguration() -> TelemetryConfiguration {
        queue.sync { configuration }
    }

    var shouldAutoConnectOnLaunch: Bool {
        queue.sync { configuration.shouldAutoConnect }
    }

    func sendLifecycle(_ messageType: TouchTelemetryMessageType, sessionId: UUID, deviceType: String, inputType: String = "unknown", exportExpected: Bool) {
        let message = TouchTelemetryMessage.lifecycle(
            messageType: messageType,
            sessionId: sessionId,
            deviceType: deviceType,
            inputType: inputType,
            exportExpected: exportExpected
        )
        enqueue(message)
    }

    func sendTouchEvent(
        _ event: TouchEvent,
        sampleKind: TouchSampleKind,
        sampleIndex: Int,
        sampleCount: Int,
        deviceType: String,
        inputType: String,
        exportExpected: Bool,
        pinMetadata: TouchPinMetadata? = nil
    ) {
        let message = TouchTelemetryMessage.touchEvent(
            sessionId: event.sessionId,
            touchId: event.touchId,
            timestamp: event.timestamp,
            phase: event.phase,
            x: event.x,
            y: event.y,
            force: event.force,
            maximumPossibleForce: event.maximumPossibleForce,
            majorRadius: event.majorRadius,
            altitudeAngle: event.altitudeAngle,
            azimuthAngle: event.azimuthAngle,
            coalescedCount: event.coalescedTouchesCount,
            predictedCount: event.predictedTouchesCount,
            deviceType: deviceType,
            inputType: inputType,
            exportExpected: exportExpected,
            sampleKind: sampleKind,
            sampleIndex: sampleIndex,
            sampleCount: sampleCount,
            pinMetadata: pinMetadata
        )
        enqueue(message)
    }

    func sendPINKeypadEvent(
        sessionId: UUID,
        touchId: UUID,
        timestamp: Double,
        phase: TouchPhase,
        x: Double,
        y: Double,
        force: Double?,
        maximumPossibleForce: Double,
        majorRadius: Double,
        altitudeAngle: Double?,
        azimuthAngle: Double?,
        coalescedCount: Int,
        predictedCount: Int,
        deviceType: String,
        inputType: String,
        exportExpected: Bool,
        pinMetadata: TouchPinMetadata
    ) {
        let message = TouchTelemetryMessage.touchEvent(
            sessionId: sessionId,
            touchId: touchId,
            timestamp: timestamp,
            phase: phase,
            x: x,
            y: y,
            force: force,
            maximumPossibleForce: maximumPossibleForce,
            majorRadius: majorRadius,
            altitudeAngle: altitudeAngle,
            azimuthAngle: azimuthAngle,
            coalescedCount: coalescedCount,
            predictedCount: predictedCount,
            deviceType: deviceType,
            inputType: inputType,
            exportExpected: exportExpected,
            sampleKind: .live,
            sampleIndex: pinMetadata.digitIndex ?? 0,
            sampleCount: 1,
            pinMetadata: pinMetadata
        )
        enqueue(message)
    }

    func snapshot() -> LiveTelemetrySnapshot {
        queue.sync {
            LiveTelemetrySnapshot(
                connectionState: connectionState,
                host: configuration.host,
                port: configuration.port,
                currentSessionId: currentSessionId,
                eventsSent: eventsSent,
                bufferedMessages: pendingMessages.count,
                droppedMessages: droppedMessages,
                lastError: lastError
            )
        }
    }

    func runConnectionTest(timeout: TimeInterval = 3.0, completion: @escaping (TelemetryConnectionTestResult) -> Void) {
        queue.async {
            let host = self.configuration.host.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !host.isEmpty else {
                DispatchQueue.main.async {
                    completion(
                        TelemetryConnectionTestResult(
                            status: .invalidHost,
                            message: "Host is empty.",
                            suggestion: "Enter the Mac LAN IP shown in Touchprint Analyzer."
                        )
                    )
                }
                return
            }
            guard Self.isValidHost(host), let port = NWEndpoint.Port(rawValue: self.configuration.port) else {
                DispatchQueue.main.async {
                    completion(
                        TelemetryConnectionTestResult(
                            status: .invalidHost,
                            message: "Invalid host or port.",
                            suggestion: "Use a valid Mac LAN IP and a numeric port."
                        )
                    )
                }
                return
            }

            let connection = NWConnection(host: NWEndpoint.Host(host), port: port, using: .tcp)
            var finished = false
            let finish: (TelemetryConnectionTestResult) -> Void = { result in
                guard !finished else { return }
                finished = true
                connection.cancel()
                DispatchQueue.main.async {
                    completion(result)
                }
            }
            let timeoutItem = DispatchWorkItem {
                finish(
                    TelemetryConnectionTestResult(
                        status: .timeout,
                        message: "Connection timed out at \(host):\(self.configuration.port).",
                        suggestion: "Check Wi-Fi isolation, VPN, firewall, and the Mac LAN IP."
                    )
                )
            }
            self.queue.asyncAfter(deadline: .now() + timeout, execute: timeoutItem)

            connection.stateUpdateHandler = { state in
                self.queue.async {
                    switch state {
                    case .ready:
                        timeoutItem.cancel()
                        finish(
                            TelemetryConnectionTestResult(
                                status: .success,
                                message: "Connection successful.",
                                suggestion: "Use this host in Touchprint Logger."
                            )
                        )
                    case .failed(let error):
                        timeoutItem.cancel()
                        finish(self.classifyConnectionTestError(error, host: host, port: self.configuration.port))
                    case .waiting(let error):
                        let result = self.classifyConnectionTestError(error, host: host, port: self.configuration.port)
                        if result.status == .permissionLikelyDenied {
                            timeoutItem.cancel()
                            finish(result)
                        }
                    case .cancelled:
                        break
                    default:
                        break
                    }
                }
            }
            connection.start(queue: self.queue)
        }
    }

    private func enqueue(_ message: TouchTelemetryMessage) {
        queue.async {
            self.currentSessionId = message.sessionId
            do {
                var data = try JSONSerialization.data(withJSONObject: message.jsonObject(), options: [.sortedKeys])
                data.append(0x0A)
                self.pendingMessages.append(data)
                self.trimBufferIfNeeded()
                self.flushIfNeeded()
            } catch {
                self.lastError = error.localizedDescription
            }
        }
    }

    private func trimBufferIfNeeded() {
        while pendingMessages.count > bufferLimit {
            pendingMessages.removeFirst()
            droppedMessages += 1
        }
    }

    private func connectLocked() {
        reconnectWorkItem?.cancel()
        reconnectWorkItem = nil
        guard connectionState != .connected else {
            flushIfNeeded()
            return
        }
        guard !configuration.host.isEmpty else {
            self.connectionState = .failed
            self.lastError = "Telemetry host is empty. Use the Mac LAN IP address, not 127.0.0.1."
            return
        }
        guard Self.isValidHost(configuration.host) else {
            self.connectionState = .failed
            self.lastError = "Invalid telemetry host '\(configuration.host)'. Use the Mac LAN IP address on a real device or 127.0.0.1 in the simulator."
            return
        }
        guard let port = NWEndpoint.Port(rawValue: configuration.port) else {
            self.connectionState = .failed
            self.lastError = "Invalid telemetry port \(configuration.port)."
            return
        }
        connectionState = .connecting
        let connection = NWConnection(host: NWEndpoint.Host(configuration.host), port: port, using: .tcp)
        self.connection = connection
        connection.stateUpdateHandler = { [weak self] state in
            guard let self else { return }
            self.queue.async {
                switch state {
                case .ready:
                    self.connectionState = .connected
                    self.lastError = nil
                    self.flushIfNeeded()
                case .failed(let error):
                    self.connectionState = .failed
                    self.lastError = TelemetryConfiguration.diagnosticMessage(for: error, host: self.configuration.host, port: self.configuration.port)
                    self.scheduleReconnect()
                case .waiting(let error):
                    self.connectionState = .waiting
                    self.lastError = TelemetryConfiguration.diagnosticMessage(for: error, host: self.configuration.host, port: self.configuration.port)
                    self.scheduleReconnect()
                case .cancelled:
                    self.connectionState = .disconnected
                    if self.autoReconnectEnabled {
                        self.scheduleReconnect()
                    }
                default:
                    break
                }
            }
        }
        connection.start(queue: queue)
    }

    private func classifyConnectionTestError(_ error: NWError, host: String, port: UInt16) -> TelemetryConnectionTestResult {
        switch error {
        case .posix(.ECONNREFUSED):
            return TelemetryConnectionTestResult(
                status: .refused,
                message: "Connection refused at \(host):\(port).",
                suggestion: "Check that the Python server is running on 0.0.0.0 and that \(host) is the Mac LAN IP."
            )
        case .posix(.ETIMEDOUT):
            return TelemetryConnectionTestResult(
                status: .timeout,
                message: "Connection timed out at \(host):\(port).",
                suggestion: "Check Wi-Fi isolation, VPN, firewall, and the Mac LAN IP."
            )
        case .posix(.ENETUNREACH), .posix(.EHOSTUNREACH):
            return TelemetryConnectionTestResult(
                status: .noRoute,
                message: "No route to host \(host):\(port).",
                suggestion: "Check that the iPhone/iPad is on the same Wi-Fi and use the Mac LAN IP."
            )
        case .posix(.EPERM):
            return TelemetryConnectionTestResult(
                status: .permissionLikelyDenied,
                message: "Local network permission may be denied.",
                suggestion: "Open iOS Settings, allow Local Network permission for Touchprint Logger, and retry."
            )
        default:
            return TelemetryConnectionTestResult(
                status: .failed,
                message: error.localizedDescription,
                suggestion: "Check the host, port, and local network permission."
            )
        }
    }

    private static func isValidHost(_ host: String) -> Bool {
        let trimmed = host.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return false }
        return trimmed.rangeOfCharacter(from: .whitespacesAndNewlines) == nil
    }

    private func scheduleReconnect() {
        guard autoReconnectEnabled else { return }
        guard reconnectWorkItem == nil else { return }
        connectionState = .reconnecting
        let workItem = DispatchWorkItem { [weak self] in
            guard let self else { return }
            self.connectLocked()
        }
        reconnectWorkItem = workItem
        queue.asyncAfter(deadline: .now() + 1.0, execute: workItem)
    }

    private func flushIfNeeded() {
        guard connectionState == .connected else {
            if connection == nil, autoReconnectEnabled, !configuration.host.isEmpty {
                connectLocked()
            }
            return
        }
        guard let connection = connection, !pendingMessages.isEmpty else { return }

        let data = pendingMessages[0]
        connection.send(content: data, completion: .contentProcessed { [weak self] error in
            guard let self else { return }
            self.queue.async {
                if let error {
                    self.connectionState = .failed
                    self.lastError = error.localizedDescription
                    self.scheduleReconnect()
                    return
                }
                self.eventsSent += 1
                if !self.pendingMessages.isEmpty {
                    self.pendingMessages.removeFirst()
                }
                self.flushIfNeeded()
            }
        })
    }
}
