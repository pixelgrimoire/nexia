"use client";

import React, { useCallback, useMemo, useRef, useState, useEffect } from "react";
import ReactFlow, {
  addEdge,
  Background,
  Connection,
  Controls,
  Edge,
  MiniMap,
  Node,
  Position,
  useEdgesState,
  useNodesState,
  Handle,
} from "reactflow";
import "reactflow/dist/style.css";
import {
  Zap,
  MessageSquare,
  GitBranch,
  Clock3,
  Tag as TagIcon,
  PlayCircle,
  Settings2,
  Bot,
} from "lucide-react";
import { useRouter } from "next/navigation";
import Toast from "../../components/Toast";
import { getAccessToken } from "../../lib/auth";
import { type JWT, createFlow } from "../../lib/api";

function NodeShell({
  color,
  title,
  subtitle,
  icon,
  children,
}: {
  color: string;
  title: string;
  subtitle?: string;
  icon: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <div className={`rounded-2xl shadow-xl border text-white ${color} min-w-[220px]`}>
      <div className="flex items-center gap-2 px-4 py-2 rounded-t-2xl">
        <div className="p-1.5 bg-white/20 rounded-lg">{icon}</div>
        <div className="leading-tight">
          <div className="font-semibold text-sm">{title}</div>
          {subtitle ? (
            <div className="text-[11px] opacity-90">{subtitle}</div>
          ) : null}
        </div>
      </div>
      {children ? (
        <div className="px-4 pb-3 pt-2 text-[12px] bg-black/10 rounded-b-2xl">{children}</div>
      ) : null}
    </div>
  );
}

function TriggerNode({ data }: any) {
  return (
    <div>
      <Handle type="source" position={Position.Bottom} />
      <NodeShell color="bg-sky-600" title={data.label || "Trigger"} subtitle={data.subtitle} icon={<Zap size={16} />}> 
        <div>{data.description || "When conversation starts or a rule matches."}</div>
      </NodeShell>
    </div>
  );
}

function MessageNode({ data }: any) {
  return (
    <div>
      <Handle type="target" position={Position.Top} />
      <Handle type="source" position={Position.Bottom} />
      <NodeShell color="bg-emerald-600" title={data.label || "Send message"} subtitle="Response" icon={<MessageSquare size={16} />}> 
        <div className="line-clamp-2">{data.description || "Hi! How can I help you today?"}</div>
      </NodeShell>
    </div>
  );
}

function ConditionNode({ data }: any) {
  return (
    <div>
      <Handle type="target" position={Position.Top} />
      <Handle type="source" position={Position.Bottom} id="yes" />
      <Handle type="source" position={Position.Right} id="no" />
      <NodeShell color="bg-violet-600" title={data.label || "If / Branch"} subtitle="Condition" icon={<GitBranch size={16} />}> 
        <div>{data.description || "If order found then Yes else No."}</div>
      </NodeShell>
    </div>
  );
}

function ActionNode({ data }: any) {
  return (
    <div>
      <Handle type="target" position={Position.Top} />
      <Handle type="source" position={Position.Bottom} />
      <NodeShell color="bg-amber-600" title={data.label || "Run Action"} subtitle="Action" icon={<Settings2 size={16} />}> 
        <div>{data.description || "Call API • Update status • Add tag"}</div>
      </NodeShell>
    </div>
  );
}

function DelayNode({ data }: any) {
  return (
    <div>
      <Handle type="target" position={Position.Top} />
      <Handle type="source" position={Position.Bottom} />
      <NodeShell color="bg-orange-600" title={data.label || "Wait"} subtitle="Delay" icon={<Clock3 size={16} />}> 
        <div>{data.description || "Wait 10 minutes before retrying."}</div>
      </NodeShell>
    </div>
  );
}

function TagNode({ data }: any) {
  return (
    <div>
      <Handle type="target" position={Position.Top} />
      <Handle type="source" position={Position.Bottom} />
      <NodeShell color="bg-teal-600" title={data.label || "Tag conversation"} subtitle="CRM" icon={<TagIcon size={16} />}> 
        <div>{data.description || "Add tag: high-value"}</div>
      </NodeShell>
    </div>
  );
}

const nodeTypes = {
  trigger: TriggerNode,
  message: MessageNode,
  condition: ConditionNode,
  action: ActionNode,
  delay: DelayNode,
  tag: TagNode,
};

const startNodes: Node[] = [
  {
    id: "t1",
    type: "trigger",
    data: { label: "Trigger", subtitle: "When customer opens", description: "Channel: WhatsApp • Keyword: 'status'" },
    position: { x: 130, y: 40 },
  },
  {
    id: "m1",
    type: "message",
    data: { label: "Ask for order", description: "Hi! What's your order number?" },
    position: { x: 130, y: 180 },
  },
  {
    id: "c1",
    type: "condition",
    data: { label: "Order exists?", description: "Query OMS API by order number" },
    position: { x: 130, y: 330 },
  },
  {
    id: "a1",
    type: "action",
    data: { label: "Send Status", description: "Return tracking + ETA" },
    position: { x: -60, y: 500 },
  },
  {
    id: "m2",
    type: "message",
    data: { label: "Not found", description: "Hm, I couldn't find it. Want to talk to an agent?" },
    position: { x: 300, y: 500 },
  },
  {
    id: "tag1",
    type: "tag",
    data: { label: "Tag: human", description: "Mark conversation for human follow-up" },
    position: { x: 300, y: 650 },
  },
  {
    id: "d1",
    type: "delay",
    data: { label: "Wait + retry", description: "Wait 10m then re-check status" },
    position: { x: -60, y: 650 },
  },
];

const startEdges: Edge[] = [
  { id: "e1", source: "t1", target: "m1" },
  { id: "e2", source: "m1", target: "c1" },
  { id: "e3", source: "c1", sourceHandle: "yes", target: "a1" },
  { id: "e4", source: "c1", sourceHandle: "no", target: "m2" },
  { id: "e5", source: "m2", target: "tag1" },
  { id: "e6", source: "a1", target: "d1" },
];

function PaletteItem({ icon, label, type }: { icon: React.ReactNode; label: string; type: string }) {
  const onDragStart = (event: React.DragEvent) => {
    event.dataTransfer.setData("application/reactflow", type);
    event.dataTransfer.effectAllowed = "move";
  };
  return (
    <div
      draggable
      onDragStart={onDragStart}
      className="flex items-center gap-2 px-3 py-2 rounded-xl border bg-white hover:bg-slate-50 cursor-grab active:cursor-grabbing select-none shadow-sm"
      title={`Drag ${label}`}
    >
      <div className="p-1.5 rounded-md bg-slate-900 text-white">{icon}</div>
      <div className="text-sm font-medium">{label}</div>
    </div>
  );
}

export default function NexIAFlowBuilder() {
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const [flowName, setFlowName] = useState("Order Status Chatbot");
  const router = useRouter();
  const [token, setToken] = useState<JWT | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [toast, setToast] = useState<{ msg: string; type?: "info" | "success" | "error" } | null>(null);

  const [nodes, setNodes, onNodesChange] = useNodesState(startNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(startEdges);
  const [reactFlowInstance, setReactFlowInstance] = useState<any>(null);
  const [selected, setSelected] = useState<Node | null>(null);

  const onConnect = useCallback((params: Edge | Connection) => setEdges((eds) => addEdge({ ...params, animated: false }, eds)), [setEdges]);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      if (!reactFlowInstance || !wrapperRef.current) return;
      const type = event.dataTransfer.getData("application/reactflow");
      if (!type) return;
      const bounds = wrapperRef.current.getBoundingClientRect();
      const position = reactFlowInstance.project({ x: event.clientX - bounds.left, y: event.clientY - bounds.top });
      const id = Math.random().toString(36).slice(2, 9);
      const defaults: Record<string, any> = {
        trigger: { label: "Trigger", subtitle: "When…", description: "Describe the event" },
        message: { label: "Send message", description: "Type a reply…" },
        condition: { label: "Condition", description: "If … then …" },
        action: { label: "Action", description: "Do something" },
        delay: { label: "Wait", description: "Delay …" },
        tag: { label: "Tag", description: "Add a tag" },
      };
      const newNode: Node = { id, type, position, data: defaults[type] || { label: type } };
      setNodes((nds) => nds.concat(newNode));
    },
    [reactFlowInstance, setNodes]
  );

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  const onSelectionChange = useCallback(({ nodes: selNodes }: { nodes: Node[] }) => {
    setSelected(selNodes[0] || null);
  }, []);

  const nodeTypesMemo = useMemo(() => nodeTypes, []);

  // Compile ReactFlow graph -> Engine graph (nodes + paths)
  function compileGraph() {
    type RFNode = Node & { data?: any };
    type RFEdge = Edge & { sourceHandle?: string | null };
    const nmap: Record<string, RFNode> = Object.fromEntries(nodes.map((n) => [n.id, n as RFNode]));
    const out: Record<string, RFEdge[]> = {};
    (edges as RFEdge[]).forEach((e) => {
      out[e.source] = out[e.source] || [];
      out[e.source].push(e);
    });

    const start = (nodes.find((n) => n.type === "trigger") || nodes[0]) as RFNode | undefined;
    const visitedGlobal = new Set<string>();

    const parseText = (node: RFNode) =>
      (node.data?.description as string) || (node.data?.label as string) || "Mensaje";

    const parseDelaySeconds = (node: RFNode) => {
      // naive parse: look for number in description; default 10s
      const d = String(node.data?.description || "");
      const m = d.match(/(\d+)(?:\s*(s|sec|secs|m|min|mins|ms))?/i);
      if (!m) return 10;
      const num = parseInt(m[1], 10);
      const unit = (m[2] || "s").toLowerCase();
      if (unit.startsWith("m") && unit !== "ms") return num * 60; // minutes
      if (unit === "ms") return Math.max(1, Math.floor(num / 1000));
      return num; // seconds
    };

    const parseTagValue = (node: RFNode) => {
      const l = String(node.data?.label || "");
      const d = String(node.data?.description || "");
      let v = l.replace(/^Tag:\s*/i, "").trim();
      if (!v && /tag[:\s]/i.test(d)) {
        const m = d.match(/tag[:\s]*([\w-]+)/i);
        if (m) v = m[1];
      }
      return v || "tagged";
    };

    const collectLinear = (fromId: string, guard: Set<string>): any[] => {
      const steps: any[] = [];
      let curId: string | undefined = fromId;
      while (curId && nmap[curId] && !guard.has(curId)) {
        guard.add(curId);
        const node = nmap[curId];
        const outs = (out[curId] || []) as RFEdge[];
        if (node.type === "message") {
          steps.push({ type: "action", action: "send_text", text: parseText(node) });
          curId = outs[0]?.target;
          continue;
        }
        if (node.type === "action") {
          // generic action → send_text (placeholder)
          steps.push({ type: "action", action: "send_text", text: parseText(node) });
          curId = outs[0]?.target;
          continue;
        }
        if (node.type === "delay") {
          steps.push({ type: "wait", seconds: parseDelaySeconds(node) });
          curId = outs[0]?.target;
          continue;
        }
        if (node.type === "tag") {
          steps.push({ type: "set_attribute", key: "tag", value: parseTagValue(node) });
          curId = outs[0]?.target;
          continue;
        }
        if (node.type === "condition") {
          // stop linear here; branching handled at top level by compile
          break;
        }
        // default: move to next if any
        curId = outs[0]?.target;
      }
      return steps;
    };

    // Branching: if a condition node is present after the first hop, compile yes/no into separate paths
    let defaultPathKey = "path_default";
    const paths: Record<string, any[]> = {};
    const mapping: Record<string, string> = {};

    if (!start) {
      // empty graph -> minimal
      paths[defaultPathKey] = [{ type: "action", action: "send_text", text: "Hola!" }];
      mapping.default = defaultPathKey;
    } else {
      const firstOut = (out[start.id] || [])[0];
      const nextId = firstOut?.target;
      const nextNode = nextId ? (nmap[nextId] as RFNode) : undefined;
      if (nextNode?.type === "condition") {
        const outs = (out[nextNode.id] || []) as RFEdge[];
        const yesTarget = outs.find((e) => (e.sourceHandle || "").toLowerCase() === "yes")?.target || outs[0]?.target;
        const noTarget = outs.find((e) => (e.sourceHandle || "").toLowerCase() === "no")?.target || outs[1]?.target;
        const yesSteps = yesTarget ? collectLinear(yesTarget, new Set<string>([start.id, nextNode.id])) : [];
        const noSteps = noTarget ? collectLinear(noTarget, new Set<string>([start.id, nextNode.id])) : [];
        if (yesSteps.length) {
          paths["path_yes"] = yesSteps;
          defaultPathKey = "path_yes";
        }
        if (noSteps.length) {
          paths["path_no"] = noSteps;
        }
        // intent map: greet → yes, pricing → no, default → primary
        mapping.default = defaultPathKey;
        if (paths["path_yes"]) mapping.greeting = "path_yes";
        if (paths["path_no"]) mapping.pricing = "path_no";
      } else {
        const seq = nextId ? collectLinear(nextId, visitedGlobal) : [];
        paths[defaultPathKey] = seq.length ? seq : [{ type: "action", action: "send_text", text: "Hola!" }];
        mapping.default = defaultPathKey;
        mapping.greeting = defaultPathKey;
        mapping.pricing = defaultPathKey;
      }
    }

    const engineGraph = {
      name: (flowName || "Untitled").trim(),
      nodes: [
        { id: "t1", type: "trigger", on: "message_in" },
        { id: "i1", type: "intent", map: mapping },
      ],
      paths,
    } as Record<string, unknown>;
    return engineGraph;
  }

  const persistJSON = () => {
    const payload = JSON.stringify(compileGraph(), null, 2);
    const blob = new Blob([payload], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${flowName.replace(/\s+/g, "_")}.graph.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  useEffect(() => {
    const t = getAccessToken() as JWT | null;
    setToken(t);
  }, []);

  const onPublish = async () => {
    if (!token) {
      setToast({ msg: "Inicia sesión para publicar", type: "error" });
      router.push("/auth/login");
      return;
    }
    setPublishing(true);
    try {
      const name = flowName.trim() || "Untitled";
      const graph = compileGraph();
      await createFlow(token, { name, version: 1, graph, status: "active" });
      setToast({ msg: "Flujo publicado", type: "success" });
      router.push("/flows");
    } catch (e: any) {
      setToast({ msg: e?.message || "Error al publicar", type: "error" });
    } finally {
      setPublishing(false);
    }
  };

  return (
    <div className="h-[80vh] w-full bg-slate-100 text-slate-900 rounded-xl overflow-hidden border">
      <div className="h-12 border-b bg-white flex items-center justify-between px-4 gap-4">
        <div className="flex items-center gap-3">
          <div className="font-bold tracking-tight text-lg">Flow Builder</div>
          <div className="hidden md:block w-px h-6 bg-slate-200" />
          <input
            className="px-3 py-1.5 rounded-lg border bg-white outline-none focus:ring-2 focus:ring-slate-300 text-sm"
            value={flowName}
            onChange={(e) => setFlowName(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-2">
          <button onClick={persistJSON} className="px-3 py-1.5 rounded-lg border bg-white hover:bg-slate-50 text-sm shadow-sm">
            Save JSON
          </button>
          <button onClick={onPublish} disabled={publishing} className="px-3 py-1.5 rounded-lg bg-slate-900 text-white hover:bg-slate-800 text-sm shadow disabled:opacity-60">
            <div className="flex items-center gap-1"><PlayCircle size={16}/>{publishing ? "Publishing…" : "Publish"}</div>
          </button>
        </div>
      </div>

      <div className="h-[calc(80vh-48px)] grid grid-cols-12">
        <aside className="col-span-3 lg:col-span-2 border-r bg-white p-3 space-y-3 overflow-y-auto">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Palette</div>
          <div className="grid gap-2">
            <PaletteItem type="trigger" label="Trigger" icon={<Zap size={16} />} />
            <PaletteItem type="message" label="Message" icon={<MessageSquare size={16} />} />
            <PaletteItem type="condition" label="Condition" icon={<GitBranch size={16} />} />
            <PaletteItem type="action" label="Action" icon={<Settings2 size={16} />} />
            <PaletteItem type="delay" label="Delay" icon={<Clock3 size={16} />} />
            <PaletteItem type="tag" label="Tag" icon={<TagIcon size={16} />} />
          </div>

          <div className="pt-4 text-xs text-slate-500 space-y-1">
            <div className="font-medium text-slate-600">How to use</div>
            <p>Drag blocks into the canvas and connect them with lines. Select a block to edit it.</p>
          </div>
        </aside>

        <main className="col-span-6 lg:col-span-8 relative" ref={wrapperRef}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            nodeTypes={nodeTypesMemo}
            onInit={setReactFlowInstance}
            onDrop={onDrop}
            onDragOver={onDragOver}
            onSelectionChange={onSelectionChange}
            fitView
            fitViewOptions={{ padding: 0.2 }}
          >
            <Background gap={20} size={1} />
            <MiniMap pannable zoomable />
            <Controls position="bottom-right" />
          </ReactFlow>
        </main>

        <aside className="col-span-3 lg:col-span-2 border-l bg-white p-3 overflow-y-auto">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Inspector</div>
          {!selected ? (
            <div className="text-sm text-slate-500 mt-2">Select a node to edit its properties.</div>
          ) : (
            <div className="space-y-3 mt-3">
              <div className="text-sm font-medium">{selected.type?.toUpperCase()}</div>
              <div className="grid gap-2">
                <label className="text-xs text-slate-600">Title</label>
                <input
                  className="px-3 py-2 rounded-lg border bg-white outline-none focus:ring-2 focus:ring-slate-300 text-sm"
                  value={(selected.data as any)?.label || ""}
                  onChange={(e) => {
                    const v = e.target.value;
                    setNodes((nds) => nds.map((n) => (n.id === selected.id ? { ...n, data: { ...n.data, label: v } } : n)));
                    setSelected((prev) => (prev ? { ...prev, data: { ...(prev.data as any), label: v } } : prev));
                  }}
                />
              </div>
              <div className="grid gap-2">
                <label className="text-xs text-slate-600">Description</label>
                <textarea
                  rows={5}
                  className="px-3 py-2 rounded-lg border bg-white outline-none focus:ring-2 focus:ring-slate-300 text-sm"
                  value={(selected.data as any)?.description || ""}
                  onChange={(e) => {
                    const v = e.target.value;
                    setNodes((nds) => nds.map((n) => (n.id === selected.id ? { ...n, data: { ...n.data, description: v } } : n)));
                    setSelected((prev) => (prev ? { ...prev, data: { ...(prev.data as any), description: v } } : prev));
                  }}
                />
              </div>
              <div className="flex gap-2">
                <button
                  className="px-3 py-1.5 rounded-lg border bg-white hover:bg-slate-50 text-sm"
                  onClick={() => {
                    setNodes((nds) => nds.filter((n) => n.id !== selected.id));
                    setEdges((eds) => eds.filter((e) => e.source !== selected.id && e.target !== selected.id));
                    setSelected(null);
                  }}
                >
                  Delete
                </button>
                <button
                  className="px-3 py-1.5 rounded-lg bg-slate-900 text-white hover:bg-slate-800 text-sm"
                  onClick={() => {
                    const dupeId = Math.random().toString(36).slice(2, 9);
                    const dupe: Node = {
                      ...(selected as Node),
                      id: dupeId,
                      position: { x: (selected as Node).position.x + 40, y: (selected as Node).position.y + 40 },
                    } as Node;
                    setNodes((nds) => nds.concat(dupe));
                  }}
                >
                  Duplicate
                </button>
              </div>
            </div>
          )}

          <div className="mt-6 text-xs text-slate-500">
            <div className="font-medium text-slate-600 mb-1">Tips</div>
            <ul className="list-disc pl-5 space-y-1">
              <li>Drag from a node handle to connect steps.</li>
              <li>Use the MiniMap to navigate long flows.</li>
              <li>"Save JSON" exports the graph schema.</li>
            </ul>
          </div>
        </aside>
      </div>
      <Toast message={toast?.msg || null} type={toast?.type} onClose={() => setToast(null)} />
    </div>
  );
}
