package com.dramafactory.service;
import com.dramafactory.dto.canvas.*;

import com.dramafactory.exception.CanvasConflictException;
import com.dramafactory.exception.ResourceNotFoundException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

class CanvasSlice1ServiceTest {

    private final ObjectMapper om = new ObjectMapper();

    static class CapturingSseEmitter extends SseEmitter {
        final List<Object> payloads = Collections.synchronizedList(new ArrayList<>());
        final List<MediaType> mediaTypes = Collections.synchronizedList(new ArrayList<>());

        @Override
        public void send(Object object, MediaType mediaType) throws IOException {
            payloads.add(object);
            mediaTypes.add(mediaType);
        }

        @Override
        public void send(Object object) throws IOException {
            payloads.add(object);
        }
    }

    static class CapturingEventService extends CanvasEventService {
        final CapturingSseEmitter emitter = new CapturingSseEmitter();
        final List<String> names = Collections.synchronizedList(new ArrayList<>());
        final List<Map<String, Object>> datas = Collections.synchronizedList(new ArrayList<>());

        @Override
        public SseEmitter subscribe(int version) {
            return emitter;
        }

        @Override
        public void broadcast(String name, Map<String, Object> data) {
            names.add(name);
            datas.add(data);
        }
    }

    private CanvasProjectService newService(Path dir, CanvasEventService events) {
        return new CanvasProjectService(dir.toString(), om, events, new CanvasMigrationAdapter(om));
    }

    private ObjectNode projectBody(int base, ArrayNode nodes, ArrayNode edges) {
        ObjectNode p = om.createObjectNode();
        p.put("schema_version", 2);
        p.set("nodes", nodes);
        p.set("edges", edges);
        p.put("base_version", base);
        return p;
    }

    private ObjectNode node(String id, String status) {
        ObjectNode n = om.createObjectNode();
        n.put("id", id);
        n.put("kind", "video");
        n.put("label", "L-" + id);
        n.put("x", 1);
        n.put("y", 2);
        n.put("status", status);
        return n;
    }

    private ObjectNode patchOp(String op, String nodeId, ObjectNode fields) {
        ObjectNode o = om.createObjectNode();
        o.put("op", op);
        o.put("node_id", nodeId);
        if (fields != null) o.set("fields", fields);
        return o;
    }

    private CanvasPatchRequest patchRequest(int base, ObjectNode... ops) {
        ArrayNode arr = om.createArrayNode();
        for (ObjectNode o : ops) arr.add(o);
        ObjectNode req = om.createObjectNode();
        req.put("base_version", base);
        req.set("ops", arr);
        return om.convertValue(req, CanvasPatchRequest.class);
    }

    @Test
    void applyPatch_happyPath_updatesStatusAndAssetRefs(@TempDir Path dir) {
        CapturingEventService events = new CapturingEventService();
        CanvasProjectService service = newService(dir, events);

        ArrayNode nodes = om.createArrayNode();
        nodes.add(node("n1", "running"));
        service.saveV2(projectBody(1, nodes, om.createArrayNode()), "editor");
        assertEquals(2, service.loadV2().version());

        ObjectNode fields = om.createObjectNode();
        fields.put("status", "done");
        ArrayNode refs = om.createArrayNode();
        refs.add("oss://a/b.mp4");
        fields.set("asset_refs", refs);

        CanvasProjectV2 updated = service.applyPatch(
                patchRequest(2, patchOp("update_node", "n1", fields)),
                null, "agent");

        assertEquals(3, updated.version());
        assertEquals("agent", updated.updatedBy());

        CanvasNodeV2 n1 = updated.nodes().stream().filter(n -> n.id().equals("n1")).findFirst().orElseThrow();
        assertEquals("done", n1.status());
        assertEquals(1, n1.assetRefs().size());
        assertEquals("oss://a/b.mp4", n1.assetRefs().get(0));

        assertTrue(events.names.contains("canvas.changed"), "应广播 canvas.changed，实际: " + events.names);
        int idx = events.names.lastIndexOf("canvas.changed");
        Map<String, Object> data = events.datas.get(idx);
        assertEquals("patch", data.get("kind"));
        assertEquals(3, ((Number) data.get("version")).intValue());
    }

    @Test
    void applyPatch_illegalOp_throwsIllegalArgument(@TempDir Path dir) {
        CapturingEventService events = new CapturingEventService();
        CanvasProjectService service = newService(dir, events);
        ArrayNode nodes = om.createArrayNode();
        nodes.add(node("n1", "running"));
        service.saveV2(projectBody(1, nodes, om.createArrayNode()), "editor");

        ObjectNode fields = om.createObjectNode();
        fields.put("status", "done");
        assertThrows(IllegalArgumentException.class, () -> service.applyPatch(
                patchRequest(2, patchOp("bogus_op", "n1", fields)), null, "agent"));
    }

    @Test
    void applyPatch_fieldsWithLabel_throwsIllegalArgument(@TempDir Path dir) {
        CapturingEventService events = new CapturingEventService();
        CanvasProjectService service = newService(dir, events);
        ArrayNode nodes = om.createArrayNode();
        nodes.add(node("n1", "running"));
        service.saveV2(projectBody(1, nodes, om.createArrayNode()), "editor");

        ObjectNode fields = om.createObjectNode();
        fields.put("label", "new label");
        assertThrows(IllegalArgumentException.class, () -> service.applyPatch(
                patchRequest(2, patchOp("update_node", "n1", fields)), null, "agent"));
    }

    @Test
    void applyPatch_invalidStatus_throwsIllegalArgument(@TempDir Path dir) {
        CapturingEventService events = new CapturingEventService();
        CanvasProjectService service = newService(dir, events);
        ArrayNode nodes = om.createArrayNode();
        nodes.add(node("n1", "running"));
        service.saveV2(projectBody(1, nodes, om.createArrayNode()), "editor");

        ObjectNode fields = om.createObjectNode();
        fields.put("status", "nonsense");
        assertThrows(IllegalArgumentException.class, () -> service.applyPatch(
                patchRequest(2, patchOp("update_node", "n1", fields)), null, "agent"));
    }

    @Test
    void applyPatch_nodeNotFound_throwsResourceNotFound(@TempDir Path dir) {
        CapturingEventService events = new CapturingEventService();
        CanvasProjectService service = newService(dir, events);
        ArrayNode nodes = om.createArrayNode();
        nodes.add(node("n1", "running"));
        service.saveV2(projectBody(1, nodes, om.createArrayNode()), "editor");

        ObjectNode fields = om.createObjectNode();
        fields.put("status", "done");
        assertThrows(ResourceNotFoundException.class, () -> service.applyPatch(
                patchRequest(2, patchOp("update_node", "missing", fields)), null, "agent"));
    }

    @Test
    void applyPatch_staleBaseVersion_throwsConflict(@TempDir Path dir) {
        CapturingEventService events = new CapturingEventService();
        CanvasProjectService service = newService(dir, events);
        ArrayNode nodes = om.createArrayNode();
        nodes.add(node("n1", "running"));
        service.saveV2(projectBody(1, nodes, om.createArrayNode()), "editor");
        service.saveV2(projectBody(2, nodes, om.createArrayNode()), "editor");

        ObjectNode fields = om.createObjectNode();
        fields.put("status", "done");
        assertThrows(CanvasConflictException.class, () -> service.applyPatch(
                patchRequest(2, patchOp("update_node", "n1", fields)), null, "agent"));
    }

    @Test
    void applyPatch_ifMatchHeaderSubstitutesBaseVersion(@TempDir Path dir) {
        CapturingEventService events = new CapturingEventService();
        CanvasProjectService service = newService(dir, events);
        ArrayNode nodes = om.createArrayNode();
        nodes.add(node("n1", "running"));
        service.saveV2(projectBody(1, nodes, om.createArrayNode()), "editor");

        ObjectNode fields = om.createObjectNode();
        fields.put("status", "done");

        ArrayNode ops = om.createArrayNode();
        ops.add(patchOp("update_node", "n1", fields));
        ObjectNode reqNode = om.createObjectNode();
        reqNode.set("ops", ops);
        CanvasPatchRequest req = om.convertValue(reqNode, CanvasPatchRequest.class);

        CanvasProjectV2 updated = service.applyPatch(req, "\"2\"", "agent");
        assertEquals(3, updated.version());
        CanvasNodeV2 n1 = updated.nodes().stream().filter(n -> n.id().equals("n1")).findFirst().orElseThrow();
        assertEquals("done", n1.status());
    }

    @Test
    void saveV2_cyclicDepends_throwsIllegalArgument(@TempDir Path dir) {
        CapturingEventService events = new CapturingEventService();
        CanvasProjectService service = newService(dir, events);

        ArrayNode nodes = om.createArrayNode();
        nodes.add(node("n1", "running"));
        nodes.add(node("n2", "running"));

        ArrayNode edges = om.createArrayNode();
        ObjectNode e1 = om.createObjectNode();
        e1.put("id", "e1");
        e1.put("source", "n1");
        e1.put("target", "n2");
        e1.put("type", "depends");
        edges.add(e1);
        ObjectNode e2 = om.createObjectNode();
        e2.put("id", "e2");
        e2.put("source", "n2");
        e2.put("target", "n1");
        e2.put("type", "depends");
        edges.add(e2);

        assertThrows(IllegalArgumentException.class,
                () -> service.saveV2(projectBody(1, nodes, edges), "editor"));
    }

    @Test
    void saveV2_invalidEdgeType_throwsIllegalArgument(@TempDir Path dir) {
        CapturingEventService events = new CapturingEventService();
        CanvasProjectService service = newService(dir, events);

        ArrayNode nodes = om.createArrayNode();
        nodes.add(node("n1", "running"));
        nodes.add(node("n2", "running"));

        ArrayNode edges = om.createArrayNode();
        ObjectNode e1 = om.createObjectNode();
        e1.put("id", "e1");
        e1.put("source", "n1");
        e1.put("target", "n2");
        e1.put("type", "xxx");
        edges.add(e1);

        assertThrows(IllegalArgumentException.class,
                () -> service.saveV2(projectBody(1, nodes, edges), "editor"));
    }

    @Test
    void proposal_createThenList(@TempDir Path dir) {
        CapturingEventService events = new CapturingEventService();
        CanvasProjectService service = newService(dir, events);

        ObjectNode body = om.createObjectNode();
        body.put("base_version", 1);
        body.set("ops", om.createArrayNode());

        CanvasProposalV2 proposal = service.createProposal(body);
        assertNotNull(proposal.id());
        assertTrue(proposal.id().startsWith("p-"), "proposal id 应以 p- 开头, 实际: " + proposal.id());
        assertEquals("pending", proposal.status());

        List<CanvasProposalV2> all = service.listProposals();
        assertEquals(1, all.size());
    }

    @Test
    void job_createAndComplete(@TempDir Path dir) throws Exception {
        CapturingEventService events = new CapturingEventService();
        CanvasProjectService service = newService(dir, events);

        ArrayNode nodes = om.createArrayNode();
        nodes.add(node("n1", "running"));
        service.saveV2(projectBody(1, nodes, om.createArrayNode()), "editor");
        int versionBefore = service.loadV2().version();

        CanvasJobService jobs = new CanvasJobService(events, service, 50L);
        CanvasJobV2 created = jobs.createJob("n1");
        assertNotNull(created.jobId());
        assertEquals("running", created.status());
        assertEquals("n1", created.nodeId());

        long deadline = System.currentTimeMillis() + 5000L;
        CanvasJobV2 current = created;
        while (System.currentTimeMillis() < deadline) {
            current = jobs.getJob(created.jobId());
            if ("done".equals(current.status())) break;
            Thread.sleep(20);
        }
        assertEquals("done", current.status(), "job 应在 5 秒内变为 done，实际: " + current.status());

        CanvasProjectV2 project = service.loadV2();
        CanvasNodeV2 n1 = project.nodes().stream().filter(n -> n.id().equals("n1")).findFirst().orElseThrow();
        assertEquals("done", n1.status());
        assertEquals(versionBefore + 1, project.version());

        boolean found = false;
        for (int i = 0; i < events.names.size(); i++) {
            if ("job.status".equals(events.names.get(i))) {
                Map<String, Object> data = events.datas.get(i);
                Object status = data.get("status");
                if ("done".equals(status) && ((Number) data.get("version")).intValue() == project.version()) {
                    found = true;
                    break;
                }
            }
        }
        assertTrue(found, "应捕获到 job.status done 事件且 data.version=" + project.version()
                + "，实际事件: " + events.names + " / " + events.datas);
    }
}
