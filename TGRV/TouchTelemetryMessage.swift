import Foundation

enum TouchTelemetryMessageType: String, Codable, Sendable {
    case touchEvent = "touch_event"
    case sessionStart = "session_start"
    case sessionEnd = "session_end"
    case reset = "reset"
    case heartbeat
}

struct TouchTelemetryMessage: Codable, Sendable {
    let messageType: TouchTelemetryMessageType
    let sessionId: String
    let newSessionId: String?
    let reason: String?
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
    let experimentMode: String?
    let pinSequenceId: String?
    let pinSequence: String?
    let digit: String?
    let digitIndex: Int?
    let keypadButtonId: String?
    let keypadAction: String?
    let expectedPin: String?
    let enteredPinSoFar: String?
    let isPinSubmit: Bool?
    let isPinClear: Bool?
    let buttonFrameX: Double?
    let buttonFrameY: Double?
    let buttonFrameWidth: Double?
    let buttonFrameHeight: Double?

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
        sampleCount: Int,
        pinMetadata: TouchPinMetadata? = nil
    ) -> TouchTelemetryMessage {
        TouchTelemetryMessage(
            messageType: .touchEvent,
            sessionId: sessionId.uuidString,
            newSessionId: nil,
            reason: nil,
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
            sampleCount: sampleCount,
            experimentMode: pinMetadata?.experimentMode,
            pinSequenceId: pinMetadata?.pinSequenceId.uuidString,
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
            newSessionId: nil,
            reason: nil,
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
            sampleCount: nil,
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
    }

    static func reset(
        sessionId: UUID,
        newSessionId: UUID,
        deviceType: String,
        reason: String = "user_reset"
    ) -> TouchTelemetryMessage {
        TouchTelemetryMessage(
            messageType: .reset,
            sessionId: sessionId.uuidString,
            newSessionId: newSessionId.uuidString,
            reason: reason,
            timestamp: Date().timeIntervalSince1970,
            deviceType: deviceType,
            exportExpected: false,
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
            inputType: "unknown",
            sampleKind: nil,
            sampleIndex: nil,
            sampleCount: nil,
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

        if let newSessionId {
            object["newSessionId"] = newSessionId as Any
        }
        if let reason {
            object["reason"] = reason as Any
        }

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
        object["experimentMode"] = experimentMode
        object["pinSequenceId"] = pinSequenceId
        object["pinSequence"] = pinSequence
        object["digit"] = digit
        object["digitIndex"] = digitIndex
        object["keypadButtonId"] = keypadButtonId
        object["keypadAction"] = keypadAction
        object["expectedPin"] = expectedPin
        object["enteredPinSoFar"] = enteredPinSoFar
        object["isPinSubmit"] = isPinSubmit
        object["isPinClear"] = isPinClear
        object["buttonFrameX"] = buttonFrameX
        object["buttonFrameY"] = buttonFrameY
        object["buttonFrameWidth"] = buttonFrameWidth
        object["buttonFrameHeight"] = buttonFrameHeight
        return object
    }
}
