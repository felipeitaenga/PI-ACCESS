import { createContext, useContext, useEffect, useRef, useState, useCallback } from "react";
import { useAuth } from "@/context/AuthContext";
import { wsUrl } from "@/lib/api";

const RealtimeContext = createContext(null);

export function RealtimeProvider({ children }) {
  const { user } = useAuth();
  const [events, setEvents] = useState([]);
  const [alarms, setAlarms] = useState([]);
  const [connected, setConnected] = useState(false);
  const [patches, setPatches] = useState({}); // atualizações de eventos já exibidos (ex.: passagem confirmada)
  const listeners = useRef(new Set());
  const wsRef = useRef(null);

  const subscribe = useCallback((fn) => {
    listeners.current.add(fn);
    return () => listeners.current.delete(fn);
  }, []);

  useEffect(() => {
    if (!user) return;
    let active = true;
    let reconnectTimer;

    const connect = () => {
      if (!active) return;
      const ws = new WebSocket(wsUrl());
      wsRef.current = ws;
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (active) reconnectTimer = setTimeout(connect, 3000);
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (msg) => {
        try {
          const payload = JSON.parse(msg.data);
          listeners.current.forEach((fn) => fn(payload));
          if (payload.type === "access_event") {
            setEvents((prev) => [payload.data, ...prev].slice(0, 100));
          } else if (payload.type === "access_event_update") {
            const { id, ...upd } = payload.data;
            setPatches((prev) => ({ ...prev, [id]: { ...(prev[id] || {}), ...upd } }));
          } else if (payload.type === "alarm") {
            setAlarms((prev) => [payload.data, ...prev].slice(0, 50));
          }
        } catch {}
      };
    };
    connect();
    return () => {
      active = false;
      clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
  }, [user]);

  return (
    <RealtimeContext.Provider value={{ events, alarms, connected, subscribe, patch: (e) => (patches[e.id] ? { ...e, ...patches[e.id] } : e) }}>
      {children}
    </RealtimeContext.Provider>
  );
}

export const useRealtime = () => useContext(RealtimeContext);
