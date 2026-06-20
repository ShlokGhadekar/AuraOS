// AuraOS · Calendar Bridge
// Usage:
//   swift scripts/calendar_bridge.swift today
//   swift scripts/calendar_bridge.swift range 7
//   swift scripts/calendar_bridge.swift calendars
//   swift scripts/calendar_bridge.swift create "<title>" "<start_iso>" "<end_iso>" "<notes>"

import EventKit
import Foundation

let store = EKEventStore()
let args = CommandLine.arguments

func requestAccess() -> Bool {
    var granted = false
    let semaphore = DispatchSemaphore(value: 0)
    if #available(macOS 14.0, *) {
        store.requestFullAccessToEvents { g, _ in
            granted = g
            semaphore.signal()
        }
    } else {
        store.requestAccess(to: .event) { g, _ in
            granted = g
            semaphore.signal()
        }
    }
    semaphore.wait()
    return granted
}

func formatEvent(_ event: EKEvent) -> [String: Any] {
    let formatter = ISO8601DateFormatter()
    return [
        "title": event.title ?? "Untitled",
        "start": formatter.string(from: event.startDate),
        "end": formatter.string(from: event.endDate),
        "calendar": event.calendar.title,
        "location": event.location ?? "",
        "notes": event.notes ?? "",
        "all_day": event.isAllDay,
    ]
}

func eventsToday() {
    let calendar = Calendar.current
    let start = calendar.startOfDay(for: Date())
    let end = calendar.date(byAdding: .day, value: 1, to: start)!
    let pred = store.predicateForEvents(withStart: start, end: end, calendars: nil)
    let events = store.events(matching: pred).map { formatEvent($0) }
    let data = try! JSONSerialization.data(withJSONObject: events)
    print(String(data: data, encoding: .utf8)!)
}

func eventsInRange(days: Int) {
    let start = Calendar.current.startOfDay(for: Date())
    let end = Calendar.current.date(byAdding: .day, value: days, to: start)!
    let pred = store.predicateForEvents(withStart: start, end: end, calendars: nil)
    let events = store.events(matching: pred).map { formatEvent($0) }
    let data = try! JSONSerialization.data(withJSONObject: events)
    print(String(data: data, encoding: .utf8)!)
}

func listCalendars() {
    let cals = store.calendars(for: .event).map { ["title": $0.title, "type": $0.type.rawValue] }
    let data = try! JSONSerialization.data(withJSONObject: cals)
    print(String(data: data, encoding: .utf8)!)
}

func createEvent(title: String, startISO: String, endISO: String, notes: String) {
    let formatter = ISO8601DateFormatter()
    guard let start = formatter.date(from: startISO),
          let end = formatter.date(from: endISO) else {
        print("{\"error\": \"Invalid date format. Use ISO8601, e.g. 2026-06-21T14:00:00Z\"}")
        exit(1)
    }

    let event = EKEvent(eventStore: store)
    event.title = title
    event.startDate = start
    event.endDate = end
    event.notes = notes.isEmpty ? nil : notes
    event.calendar = store.defaultCalendarForNewEvents

    do {
        try store.save(event, span: .thisEvent)
        let result: [String: Any] = [
            "success": true,
            "title": title,
            "start": startISO,
            "end": endISO,
            "calendar": event.calendar.title,
        ]
        let data = try! JSONSerialization.data(withJSONObject: result)
        print(String(data: data, encoding: .utf8)!)
    } catch {
        print("{\"error\": \"Failed to save event: \(error.localizedDescription)\"}")
        exit(1)
    }
}

// Main
guard requestAccess() else {
    print("{\"error\": \"Calendar access denied. Grant access in System Settings → Privacy → Calendars\"}")
    exit(1)
}

let command = args.count > 1 ? args[1] : "today"

switch command {
case "today":
    eventsToday()
case "range":
    let days = args.count > 2 ? Int(args[2]) ?? 7 : 7
    eventsInRange(days: days)
case "calendars":
    listCalendars()
case "create":
    guard args.count >= 5 else {
        print("{\"error\": \"create requires: title start_iso end_iso notes\"}")
        exit(1)
    }
    createEvent(title: args[2], startISO: args[3], endISO: args[4], notes: args.count > 5 ? args[5] : "")
default:
    print("{\"error\": \"Unknown command: \(command)\"}")
    exit(1)
}