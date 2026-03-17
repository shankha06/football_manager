import { useEffect, useRef, useCallback, useState } from 'react';
import type { WSMessage } from '../types';

interface UseWebSocketOptions {
  onMessage?: (msg: WSMessage) => void;
  onOpen?: () => void;
  onClose?: () => void;
}

export function useMatchWebSocket(options: UseWebSocketOptions = {}) {
  const wsRef = useRef<WebSocket | null>(null);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const [connected, setConnected] = useState(false);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/match`);

    ws.onopen = () => {
      setConnected(true);
      optionsRef.current.onOpen?.();
    };

    ws.onmessage = (event) => {
      try {
        const raw = JSON.parse(event.data);
        // Normalize: backend sends various shapes, unify to WSMessage
        const msg: WSMessage = {
          type: raw.type,
          minute: raw.minute,
          text: raw.text ?? raw.description ?? '',
          data: raw,
        };
        optionsRef.current.onMessage?.(msg);
      } catch {
        // ignore parse errors
      }
    };

    ws.onclose = () => {
      setConnected(false);
      optionsRef.current.onClose?.();
    };

    ws.onerror = () => {
      setConnected(false);
    };

    wsRef.current = ws;
  }, []);

  const send = useCallback((data: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  const startMatch = useCallback(() => send({ type: 'start' }), [send]);

  const makeSubstitution = useCallback((playerOff: number, playerOn: number) =>
    send({ type: 'sub', player_off: playerOff, player_on: playerOn }), [send]);

  const changeTactic = useCallback((field: string, value: string) =>
    send({ type: 'tactic_change', field, value }), [send]);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    setConnected(false);
  }, []);

  useEffect(() => {
    return () => {
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, []);

  return { connected, connect, disconnect, startMatch, makeSubstitution, changeTactic };
}
