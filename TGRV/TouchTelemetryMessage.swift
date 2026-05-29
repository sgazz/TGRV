import Foundation

enum TouchTelemetryMessageType: String, Codable, Sendable {
    case touchEvent = "touch_event"
    case sessionStart = "session_start"
    case sessionEnd = "session_end"
    case heartbeat
}

struct TouchTelemetryMessage: Codable, Sendable {
    let messageType: TouchTelemetryMessageType
    let sessionId: String
    let timestamp: Double
    let deviceType: String
    let exportExpected: Bool
    let touchId: String?
    let phase: String?
    let x: Double?
    let y: Double?
    let force: Double?
    let maximumPossibleForce: Double?
    let majorRadius: Double?
    let altitudeAngle: Double?
    let azimuthAngle: Double?
    let coalescedCount: Int?
    let predictedCount: Int?
    let inputType: String
    let sampleKind: String?
    let sampleIndex: Int?
    let sampleCount: Int?

    static func touchEvent(
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
        sampleKind: TouchSampleKind,
        sampleIndex: Int,
        sampleCount: Int
    ) -> TouchTelemetryMessage {
        TouchTelemetryMessage(
            messageType: .touchEvent,
            sessionId: sessionId.uuidString,
            timestamp: timestamp,
            deviceType: deviceType,
            exportExpected: exportExpected,
            touchId: touchId.uuidString,
            phase: phase.rawValue,
            x: x,
            y: y,
            force: force,
            maximumPossibleForce: maximumPossibleForce,
            majorRadius: majorRadius,
            altitudeAngle: altitudeAngle,
            azimuthAngle: azimuthAngle,
            coalescedCount: coalescedCount,
            predictedCount: predictedCount,
            inputType: inputType,
            sampleKind: sampleKind.rawValue,
            sampleIndex: sampleIndex,
            sampleCount: sampleCount
        )
    }

    static func lifecycle(
        messageType: TouchTelemetryMessageType,
        sessionId: UUID,
        deviceType: String,
        inputType: String = "unknown",
        exportExpected: Bool
    ) -> TouchTelemetryMessage {
        TouchTelemetryMessage(
            messageType: messageType,
            sessionId: sessionId.uuidString,
            timestamp: Date().timeIntervalSince1970,
            deviceType: deviceType,
            exportExpected: exportExpected,
            touchId: nil,
            phase: nil,
            x: nil,
            y: nil,
            force: nil,
            maximumPossibleForce: nil,
            majorRadius: nil,
            altitudeAngle: nil,
            azimuthAngle: nil,
            coalescedCount: nil,
            predictedCount: nil,
            inputType: inputType,
            sampleKind: nil,
            sampleIndex: nil,
            sampleCount: nil
        )
    }

    func jsonObject() -> [String: Any] {
        var object: [String: Any] = [
            "messageType": messageType.rawValue,
            "sessionId": sessionId,
            "timestamp": timestamp,
            "deviceType": deviceType,
            "exportExpected": exportExpected,
            "inputType": inputType,
        ]

        object["touchId"] = touchId
        object["phase"] = phase
        object["x"] = x
        object["y"] = y
        object["force"] = force
        object["maximumPossibleForce"] = maximumPossibleForce
        object["majorRadius"] = majorRadius
        object["altitudeAngle"] = altitudeAngle
        object["azimuthAngle"] = azimuthAngle
        object["coalescedCount"] = coalescedCount
        object["predictedCount"] = predictedCount
        object["sampleKind"] = sampleKind
        object["sampleIndex"] = sampleIndex
        object["sampleCount"] = sampleCount
        return object
    }
}
