// Craft Anything accessibility helper.
//
// Reads a JSON request on stdin and writes a JSON result on stdout. It walks the macOS
// accessibility (AX) tree of a running application and, for walkthroughs, performs AX actions
// between reads. It is our own clean-room code; it names no third-party product.
//
// Request shapes:
//   {"command":"observe","pid":1234,"window_id":null,"screenshot":false,"accessibility":true,"max_nodes":5000}
//   {"command":"walkthrough","pid":1234,"steps":[{"action":"AXPress","element":"Save"}],"max_nodes":5000}
//
// Compiled lazily on the host with `xcrun swiftc`; never shipped as a binary.

import Foundation
import ApplicationServices

struct Request: Decodable {
    var command: String
    var pid: Int32?
    var window_id: UInt64?
    var screenshot: Bool?
    var accessibility: Bool?
    var max_nodes: Int?
    var steps: [Step]?
}

struct Step: Decodable {
    var action: String
    var element: String
}

func attr(_ element: AXUIElement, _ name: String) -> String? {
    var value: CFTypeRef?
    if AXUIElementCopyAttributeValue(element, name as CFString, &value) == .success,
       let v = value {
        return (v as? String) ?? String(describing: v)
    }
    return nil
}

func children(_ element: AXUIElement) -> [AXUIElement] {
    var value: CFTypeRef?
    if AXUIElementCopyAttributeValue(element, kAXChildrenAttribute as CFString, &value) == .success,
       let arr = value as? [AXUIElement] {
        return arr
    }
    return []
}

func walk(_ element: AXUIElement, depth: Int, budget: inout Int, out: inout [[String: Any]]) {
    if budget <= 0 { return }
    budget -= 1
    var node: [String: Any] = ["depth": depth]
    if let role = attr(element, kAXRoleAttribute as String) { node["role"] = role }
    if let title = attr(element, kAXTitleAttribute as String) { node["title"] = title }
    if let value = attr(element, kAXValueAttribute as String) { node["value"] = value }
    if let ident = attr(element, "AXIdentifier") { node["identifier"] = ident }
    out.append(node)
    for child in children(element) {
        walk(child, depth: depth + 1, budget: &budget, out: &out)
    }
}

func snapshot(pid: Int32, maxNodes: Int) -> [[String: Any]] {
    let app = AXUIElementCreateApplication(pid)
    var out: [[String: Any]] = []
    var budget = maxNodes
    walk(app, depth: 0, budget: &budget, out: &out)
    return out
}

func findElement(_ root: AXUIElement, _ needle: String, _ budget: inout Int) -> AXUIElement? {
    if budget <= 0 { return nil }
    budget -= 1
    if attr(root, kAXTitleAttribute as String) == needle || attr(root, "AXIdentifier") == needle {
        return root
    }
    for child in children(root) {
        if let found = findElement(child, needle, &budget) { return found }
    }
    return nil
}

func emit(_ obj: [String: Any]) {
    if let data = try? JSONSerialization.data(withJSONObject: obj, options: []),
       let text = String(data: data, encoding: .utf8) {
        print(text)
    }
}

let input = FileHandle.standardInput.readDataToEndOfFile()
guard let req = try? JSONDecoder().decode(Request.self, from: input), let pid = req.pid else {
    emit(["error": "invalid request"])
    exit(2)
}

if !AXIsProcessTrusted() {
    emit(["error": "accessibility permission not granted", "nodes": []])
    exit(0)
}

switch req.command {
case "observe":
    let nodes = snapshot(pid: pid, maxNodes: req.max_nodes ?? 5000)
    emit(["nodes": nodes, "truncated": nodes.count >= (req.max_nodes ?? 5000)])
case "walkthrough":
    let app = AXUIElementCreateApplication(pid)
    var steps: [[String: Any]] = []
    let before = snapshot(pid: pid, maxNodes: req.max_nodes ?? 5000)
    for step in req.steps ?? [] {
        var budget = req.max_nodes ?? 5000
        var outcome = "element_not_found"
        if let target = findElement(app, step.element, &budget) {
            let result = AXUIElementPerformAction(target, step.action as CFString)
            outcome = result == .success ? "dispatched" : "failed"
        }
        steps.append(["action": step.action, "element": step.element, "outcome": outcome])
    }
    let after = snapshot(pid: pid, maxNodes: req.max_nodes ?? 5000)
    emit(["steps": steps, "nodes_before": before, "nodes_after": after])
default:
    emit(["error": "unknown command"])
    exit(2)
}
