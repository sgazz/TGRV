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

    func recordPINKeypadInteraction(
        touch: UITouch,
        phase: TouchPhase,
        in referenceView: UIView,
        buttonFrame: CGRect,
        pinMetadata: TouchPinMetadata,
        touchId: UUID,
        sampleKind: TouchSampleKind = .live,
        sampleIndex: Int = 0,
        sampleCount: Int = 1,
        deviceType: DeviceType? = nil,
        inputTypeOverride: String? = nil,
        event: UIEvent? = nil
    ) -> Int {
        let sessionId = SessionManager.shared.currentSessionId()
        let resolvedDeviceType = deviceType ?? Self.currentDeviceType
        let coalescedTouches = event?.coalescedTouches(for: touch) ?? []
        let predictedTouches = event?.predictedTouches(for: touch) ?? []
        let point = touch.location(in: referenceView)
        let isPressureSupported = touch.maximumPossibleForce > 0
        let force = isPressureSupported ? Double(touch.force) : nil

        let altitudeAngle: Double?
        let azimuthAngle: Double?
        switch touch.type {
        case .pencil, .stylus:
            altitudeAngle = Double(touch.altitudeAngle)
            azimuthAngle = Double(touch.azimuthAngle(in: referenceView))
        default:
            altitudeAngle = nil
            azimuthAngle = nil
        }

        return queue.sync {
            appendTouchEvent(
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
                deviceType: resolvedDeviceType,
                coalescedCount: coalescedTouches.count,
                predictedCount: predictedTouches.count,
                pinMetadata: pinMetadata
            )

            if telemetryHostConfigured {
                telemetryClient.sendPINKeypadEvent(
                    sessionId: sessionId,
                    touchId: touchId,
                    timestamp: touch.timestamp,
                    phase: phase,
                    x: Double(point.x),
                    y: Double(point.y),
                    force: force,
                    maximumPossibleForce: Double(touch.maximumPossibleForce),
                    majorRadius: Double(touch.majorRadius),
                    altitudeAngle: altitudeAngle,
                    azimuthAngle: azimuthAngle,
                    coalescedCount: coalescedTouches.count,
                    predictedCount: predictedTouches.count,
                    deviceType: Self.currentDeviceTypeString,
                    inputType: inputTypeOverride ?? Self.touchInputString(for: touch.type),
                    exportExpected: true,
                    pinMetadata: pinMetadata
                )
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

    func resetSession() -> (oldSessionId: UUID, newSessionId: UUID) {
        let oldSessionId = SessionManager.shared.currentSessionId()
        let connectedBeforeReset = telemetryClient.snapshot().connectionState == .connected
        let newSessionInfo = SessionManager.shared.resetSession()
        queue.sync {
            events.removeAll(keepingCapacity: true)
            touchStates.removeAll(keepingCapacity: true)
        }
        if telemetryHostConfigured && connectedBeforeReset {
            telemetryClient.sendReset(
                sessionId: oldSessionId,
                newSessionId: newSessionInfo.sessionId,
                deviceType: Self.currentDeviceTypeString,
                reason: "user_reset"
            )
            telemetryClient.sendLifecycle(
                .sessionStart,
                sessionId: newSessionInfo.sessionId,
                deviceType: Self.currentDeviceTypeString,
                exportExpected: true
            )
        }
        return (oldSessionId, newSessionInfo.sessionId)
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
            predictedTouchesCount: predictedCount,
            experimentMode: nil,
            pinSequenceId: nil,
            pinSequence: nil,
            digit: nil,
            digitIndex: nil,
            keypadButtonId: nil,
            keypadAction: nil,
            expectedPin: nil,
            enteredPinSoFar: nil,
            isPinSubmit: nil,
            isPinClear: nil,
            buttonFrameX: nil,
            buttonFrameY: nil,
            buttonFrameWidth: nil,
            buttonFrameHeight: nil
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
                exportExpected: true,
                pinMetadata: nil
            )
        }
    }

    private func appendTouchEvent(
        sessionId: UUID,
        touchId: UUID,
        phase: TouchPhase,
        sampleKind: TouchSampleKind,
        sampleIndex: Int,
        sampleCount: Int,
        timestamp: Double,
        x: Double,
        y: Double,
        force: Double?,
        maximumPossibleForce: Double,
        majorRadius: Double,
        altitudeAngle: Double?,
        azimuthAngle: Double?,
        touchType: TouchInputType,
        deviceType: DeviceType,
        coalescedCount: Int,
        predictedCount: Int,
        pinMetadata: TouchPinMetadata? = nil
    ) {
        let event = TouchEvent(
            id: UUID(),
            sessionId: sessionId,
            touchId: touchId,
            phase: phase,
            sampleKind: sampleKind,
            sampleIndex: sampleIndex,
            sampleCount: sampleCount,
            timestamp: timestamp,
            x: x,
            y: y,
            force: force,
            maximumPossibleForce: maximumPossibleForce,
            majorRadius: majorRadius,
            altitudeAngle: altitudeAngle,
            azimuthAngle: azimuthAngle,
            touchType: touchType,
            deviceType: deviceType,
            coalescedTouchesCount: coalescedCount,
            predictedTouchesCount: predictedCount,
            experimentMode: pinMetadata?.experimentMode,
            pinSequenceId: pinMetadata?.pinSequenceId,
            pinSequence: pinMetadata?.pinSequence,
            digit: pinMetadata?.digit,
            digitIndex: pinMetadata?.digitIndex,
            keypadButtonId: pinMetadata?.keypadButtonId,
            keypadAction: pinMetadata?.keypadAction,
            expectedPin: pinMetadata?.expectedPin,
            enteredPinSoFar: pinMetadata?.enteredPinSoFar,
            isPinSubmit: pinMetadata?.keypadAction == "submit" ? true : nil,
            isPinClear: pinMetadata?.keypadAction == "clear" ? true : nil,
            buttonFrameX: pinMetadata?.buttonFrameX,
            buttonFrameY: pinMetadata?.buttonFrameY,
            buttonFrameWidth: pinMetadata?.buttonFrameWidth,
            buttonFrameHeight: pinMetadata?.buttonFrameHeight
        )

        events.append(event)
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
