"use client";
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

const ROW_HEIGHT = 60;
const VIEWPORT = 480;
const OVERSCAN = 4;

// Fixed-height waterfall rows already use a single-line, ellipsized label.
// Small traces retain their natural layout; large traces retain every row in a scroll window.
export function VirtualSpanList({
  count,
  children,
}: {
  count: number;
  children: (start: number, end: number) => ReactNode;
}) {
  const container = useRef<HTMLDivElement>(null);
  const pendingFocus = useRef<number | null>(null);
  const [first, setFirst] = useState(0);
  const virtual = count > 100;
  const start = virtual
    ? Math.max(0, Math.min(first, count - 1) - OVERSCAN)
    : 0;
  const end = virtual
    ? Math.min(count, start + VIEWPORT / ROW_HEIGHT + OVERSCAN * 2)
    : count;

  useLayoutEffect(() => {
    if (pendingFocus.current === null) return;
    container.current
      ?.querySelector<HTMLButtonElement>(
        `[data-span-index="${pendingFocus.current}"]`,
      )
      ?.focus({ preventScroll: true });
    pendingFocus.current = null;
  }, [start, end]);

  return (
    <div
      ref={container}
      className={`span-list${virtual ? " virtual-span-list" : ""}`}
      onScroll={
        virtual
          ? (event) =>
              setFirst(Math.floor(event.currentTarget.scrollTop / ROW_HEIGHT))
          : undefined
      }
      onKeyDown={
        virtual
          ? (event) => {
              const target = (
                event.target as HTMLElement
              ).closest<HTMLButtonElement>("[data-span-index]");
              if (!target) return;
              const index = Number(target.dataset.spanIndex);
              const next =
                event.key === "ArrowDown"
                  ? Math.min(count - 1, index + 1)
                  : event.key === "ArrowUp"
                    ? Math.max(0, index - 1)
                    : event.key === "Home"
                      ? 0
                      : event.key === "End"
                        ? count - 1
                        : null;
              if (next === null) return;
              event.preventDefault();
              const list = event.currentTarget;
              const top = next * ROW_HEIGHT;
              if (top < list.scrollTop) list.scrollTop = top;
              else if (top + ROW_HEIGHT > list.scrollTop + VIEWPORT)
                list.scrollTop = top + ROW_HEIGHT - VIEWPORT;
              const button = list.querySelector<HTMLButtonElement>(
                `[data-span-index="${next}"]`,
              );
              if (button) button.focus({ preventScroll: true });
              else pendingFocus.current = next;
              setFirst(Math.floor(list.scrollTop / ROW_HEIGHT));
            }
          : undefined
      }
    >
      {virtual && (
        <p className="sr-only">
          {count} spans. Use Up and Down arrow keys, Home and End to navigate
          all spans.
        </p>
      )}
      <div
        style={
          virtual
            ? {
                paddingTop: start * ROW_HEIGHT,
                paddingBottom: (count - end) * ROW_HEIGHT,
              }
            : undefined
        }
      >
        {children(start, end)}
      </div>
    </div>
  );
}
