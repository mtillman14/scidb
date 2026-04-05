/**
 * useBackendMessage — unified hook for backend push notifications.
 *
 * In VS Code mode: listens for postMessage notifications from the extension host.
 * In standalone mode: listens for WebSocket messages.
 *
 * This replaces useWebSocket so components work in both environments.
 */

import { useEffect, useRef, useCallback } from 'react';
import { addNotificationHandler } from '../api';
import { useWebSocket } from './useWebSocket';

type MessageHandler = (msg: Record<string, unknown>) => void;

const isVSCode = typeof acquireVsCodeApi === 'function';

/**
 * Subscribe to backend push notifications (run_output, run_done, dag_updated).
 * Works in both VS Code Webview and standalone (WebSocket) modes.
 */
export function useBackendMessage(onMessage: MessageHandler) {
  const handlerRef = useRef(onMessage);
  handlerRef.current = onMessage;

  const stableHandler = useCallback((msg: Record<string, unknown>) => {
    handlerRef.current(msg);
  }, []);

  // VS Code mode: use postMessage notifications
  useEffect(() => {
    if (!isVSCode) return;
    return addNotificationHandler(stableHandler);
  }, [stableHandler]);

  // Standalone mode: use WebSocket
  // The hook is always called (React rules of hooks) but the WebSocket
  // singleton only connects in non-VS Code environments.
  useWebSocket(isVSCode ? () => {} : stableHandler);
}

declare function acquireVsCodeApi(): unknown;
