import Foundation
import UIKit

final class TouchLogger {
    static let shared = TouchLogger()

    private struct TouchState {
        var touchId: UUID
    }

    private let queue = DispatchQueue(label: "com.gazza.tgrv.touch-logger", qos: .userInitiated)
    private var events: [TouchEvent]
    private var touchStates: [ObjectIdentifier: TouchState]
    private let telemetryClient: LiveTelemetryClient
    private var telemetryHostConfigured: Bool

    private init() {
        self.events = []
        self.events.reserveCapacity(4096)
        self.touchStates = [:]
        self.telemetryClient = .shared
        self.telemetryHostConfigured = !self.telemetryClient.currentConfiguration().host.isEmpty
        if self.telemetryClient.shouldAutoConnectOnLaunch {
            self.telemetryClient.connect()
        }
    }

    func recordTouches(
        _ touches: Set<UITouch>,
        phase: TouchPhase,
        in view: UIView,
        event: UIEvent?
    ) -> Int {
        let sessionId = SessionManager.shared.currentSessionId()
        let deviceType = Self.currentDeviceType

        return queue.sync {
            for touch in touches {
                let identity = ObjectIdentifier(touch)
                let touchId = touchStates[identity]?.touchId ?? {
                    let newTouchId = UUID()
                    touchStates[identity] = TouchState(touchId: newTouchId)
                    return newTouchId
                }()

                let coalescedTouches = event?.coalescedTouches(for: touch) ?? []
                let predictedTouches = event?.predictedTouches(for: touch) ?? []

                appendSample(
                    touch: touch,
                    sessionId: sessionId,
                    touchId: touchId,
                    phase: phase,
                    sampleKind: .live,
                    sampleIndex: 0,
                    sampleCount: 1,
                    coalescedCount: coalescedTouches.count,
                    predictedCount: predictedTouches.count,
                    deviceType: deviceType,
                    view: view
                )

                if !coalescedTouches.isEmpty {
                    for (index, coalescedTouch) in coalescedTouches.enumerated() {
                        appendSample(
                            touch: coalescedTouch,
                            sessionId: sessionId,
                            touchId: touchId,
                            phase: phase,
                            sampleKind: .coalesced,
                            sampleIndex: index + 1,
                            sampleCount: coalescedTouches.count,
                            coalescedCount: coalescedTouches.count,
                            predictedCount: predictedTouches.count,
                            deviceType: deviceType,
                            view: view
                        )
                    }
                }

                if !predictedTouches.isEmpty {
                    for (index, predictedTouch) in predictedTouches.enumerated() {
                        appendSample(
                            touch: predictedTouch,
                            sessionId: sessionId,
                            touchId: touchId,
                            phase: phase,
                            sampleKind: .predicted,
                            sampleIndex: index + 1,
                            sampleCount: predictedTouches.count,
                            coalescedCount: coalescedTouches.count,
                            predictedCount: predictedTouches.count,
                            deviceType: deviceType,
                            view: view
                        )
                    }
                }

                if phase == .ended || phase == .cancelled {
                    touchStates.removeValue(forKey: identity)
                }
            }

            return events.count
        }
    }

    func eventCount() -> Int {
        queue.sync { events.count }
    }

    func currentSessionExport() -> TouchSessionExport {
        queue.sync {
            TouchSessionExport(
                sessionId: SessionManager.shared.currentSessionId(),
                startedAt: SessionManager.shared.currentSessionStartedAt(),
                exportedAt: Date().timeIntervalSince1970,
                deviceType: Self.currentDeviceType,
                touchEventCount: events.count,
                events: events
            )
        }
    }

    func exportCurrentSession() throws -> URL {
        if telemetryHostConfigured {
            telemetryClient.sendLifecycle(
                .sessionEnd,
                sessionId: SessionManager.shared.currentSessionId(),
                deviceType: Self.currentDeviceTypeString,
                exportExpected: true
            )
        }
        return try ExportManager.export(session: currentSessionExport())
    }

    func resetSession() {
        if telemetryHostConfigured {
            telemetryClient.sendLifecycle(
                .sessionEnd,
                sessionId: SessionManager.shared.currentSessionId(),
                deviceType: Self.currentDeviceTypeString,
                exportExpected: false
            )
        }
        queue.sync {
            events.removeAll(keepingCapacity: true)
            touchStates.removeAll(keepingCapacity: true)
        }
        _ = SessionManager.shared.resetSession()
        if telemetryHostConfigured {
            telemetryClient.sendLifecycle(
                .sessionStart,
                sessionId: SessionManager.shared.currentSessionId(),
                deviceType: Self.currentDeviceTypeString,
                exportExpected: true
            )
        }
    }

    func startLiveTelemetrySession() {
        guard !telemetryClient.currentConfiguration().host.isEmpty else { return }
        telemetryClient.sendLifecycle(
            .sessionStart,
            sessionId: SessionManager.shared.currentSessionId(),
            deviceType: Self.currentDeviceTypeString,
            exportExpected: true
        )
    }

    func liveTelemetrySnapshot() -> LiveTelemetrySnapshot {
        telemetryClient.snapshot()
    }

    func telemetryConfiguration() -> TelemetryConfiguration {
        telemetryClient.currentConfiguration()
    }

    func updateTelemetryConfiguration(host: String, port: UInt16, connect: Bool) {
        telemetryHostConfigured = !host.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        telemetryClient.updateConfiguration(host: host, port: port, connect: connect)
    }

    func connectLiveTelemetry() {
        telemetryClient.connect()
    }

    func disconnectLiveTelemetry() {
        telemetryClient.disconnect()
    }

    func runTelemetryConnectionTest(completion: @escaping (TelemetryConnectionTestResult) -> Void) {
        telemetryClient.runConnectionTest(completion: completion)
    }

    private func appendSample(
        touch: UITouch,
        sessionId: UUID,
        touchId: UUID,
        phase: TouchPhase,
        sampleKind: TouchSampleKind,
        sampleIndex: Int,
        sampleCount: Int,
        coalescedCount: Int,
        predictedCount: Int,
        deviceType: DeviceType,
        view: UIView
    ) {
        let point = touch.location(in: view)
        let isPressureSupported = touch.maximumPossibleForce > 0
        let force = isPressureSupported ? Double(touch.force) : nil
        let altitudeAngle: Double?
        let azimuthAngle: Double?

        switch touch.type {
        case .pencil, .stylus:
            altitudeAngle = Double(touch.altitudeAngle)
            azimuthAngle = Double(touch.azimuthAngle(in: view))
        default:
            altitudeAngle = nil
            azimuthAngle = nil
        }

        let event = TouchEvent(
            id: UUID(),
            sessionId: sessionId,
            touchId: touchId,
            phase: phase,
            sampleKind: sampleKind,
            sampleIndex: sampleIndex,
            sampleCount: sampleCount,
            timestamp: touch.timestamp,
            x: Double(point.x),
            y: Double(point.y),
            force: force,
            maximumPossibleForce: Double(touch.maximumPossibleForce),
            majorRadius: Double(touch.majorRadius),
            altitudeAngle: altitudeAngle,
            azimuthAngle: azimuthAngle,
            touchType: Self.touchInputType(for: touch.type),
            deviceType: deviceType,
            coalescedTouchesCount: coalescedCount,
            predictedTouchesCount: predictedCount
        )

        events.append(event)
        if telemetryHostConfigured {
            telemetryClient.sendTouchEvent(
                event,
                sampleKind: sampleKind,
                sampleIndex: sampleIndex,
                sampleCount: sampleCount,
                deviceType: Self.currentDeviceTypeString,
                inputType: Self.touchInputString(for: touch.type),
                exportExpected: true
            )
        }
    }

    private static func touchInputType(for type: UITouch.TouchType) -> TouchInputType {
        switch type {
        case .direct:
            return .direct
        case .pencil:
            return .pencil
        case .stylus:
            return .stylus
        case .indirect:
            return .indirect
        case .indirectPointer:
            return .indirectPointer
        @unknown default:
            return .unknown
        }
    }

    private static func touchInputString(for type: UITouch.TouchType) -> String {
        switch type {
        case .direct:
            return "finger"
        case .pencil:
            return "pencil"
        case .stylus:
            return "stylus"
        case .indirect:
            return "indirect"
        case .indirectPointer:
            return "indirectPointer"
        @unknown default:
            return "unknown"
        }
    }

    private static var currentDeviceType: DeviceType {
        switch UIDevice.current.userInterfaceIdiom {
        case .phone:
            return .phone
        case .pad:
            return .pad
        default:
            return .other
        }
    }

    private static var currentDeviceTypeString: String {
        switch UIDevice.current.userInterfaceIdiom {
        case .phone:
            return "iPhone"
        case .pad:
            return "iPad"
        default:
            return "other"
        }
    }
}
