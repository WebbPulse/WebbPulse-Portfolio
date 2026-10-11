import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import type { NavigationItem } from '../../types';

/** Props for {@link CommandMenu}. */
interface CommandMenuProps {
  open: boolean;
  onClose: () => void;
  items: NavigationItem[];
  onToggleTheme: () => void;
}

/** One row of the menu: a place to go or an action to run. */
interface Command {
  id: string;
  label: string;
  hint: string;
  run: () => void;
}

/**
 * A minimal jump menu opened by the header button or Cmd+K.
 *
 * It lists the site sections, the blog, the privacy page and the theme switch,
 * filtered by what the visitor types. Arrow keys move, Enter runs, Escape
 * closes and focus returns to whatever opened it.
 */
export const CommandMenu: React.FC<CommandMenuProps> = ({
  open,
  onClose,
  items,
  onToggleTheme,
}) => {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);

  const commands = useMemo<Command[]>(() => {
    const go = (href: string) => () => {
      onClose();
      if (href.includes('#')) {
        window.location.assign(href);
        return;
      }
      void navigate(href);
    };
    const places: Command[] = items.map((item) => ({
      id: item.href,
      label: item.label,
      hint: 'Go to',
      run: go(item.href),
    }));
    const extras: Command[] = [
      { id: '/', label: 'Home', hint: 'Go to', run: go('/') },
      { id: '/privacy', label: 'Privacy', hint: 'Go to', run: go('/privacy') },
      {
        id: 'theme',
        label: 'Switch theme',
        hint: 'Action',
        run: () => {
          onToggleTheme();
          onClose();
        },
      },
    ];
    const seen = new Set(places.map((p) => p.label));
    return [...places, ...extras.filter((e) => !seen.has(e.label))];
  }, [items, navigate, onClose, onToggleTheme]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((c) => c.label.toLowerCase().includes(q));
  }, [commands, query]);

  useEffect(() => {
    if (!open) return;
    returnFocus.current = document.activeElement as HTMLElement | null;
    setQuery('');
    setActive(0);
    inputRef.current?.focus();
    return () => returnFocus.current?.focus();
  }, [open]);

  if (!open) return null;

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((i) => (filtered.length ? (i + 1) % filtered.length : 0));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((i) =>
        filtered.length ? (i - 1 + filtered.length) % filtered.length : 0
      );
    } else if (e.key === 'Enter') {
      e.preventDefault();
      filtered[active]?.run();
    } else if (e.key === 'Tab') {
      e.preventDefault();
    }
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center px-4 pt-[12vh]"
      onKeyDown={onKeyDown}
    >
      <div
        className="absolute inset-0 bg-paper/70 backdrop-blur-[2px]"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command menu"
        className="relative w-full max-w-lg border border-line-strong bg-paper-raised shadow-[0_24px_48px_-24px_rgba(10,20,36,0.45)] motion-safe:animate-fade-in"
      >
        <div className="flex items-center gap-3 border-b border-line px-4">
          <span className="mono-label" aria-hidden="true">
            Jump
          </span>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            placeholder="Type a section or page"
            aria-label="Search the site"
            aria-controls="command-menu-list"
            aria-activedescendant={
              filtered[active] ? `cmd-${filtered[active].id}` : undefined
            }
            role="combobox"
            aria-expanded="true"
            className="h-12 w-full bg-transparent text-sm text-ink placeholder:text-ink-faint focus:outline-none"
          />
          <kbd className="mono-label border border-line px-1.5 py-0.5">Esc</kbd>
        </div>
        <ul
          id="command-menu-list"
          role="listbox"
          aria-label="Destinations"
          className="max-h-80 overflow-y-auto py-1.5 scrollbar-thin"
        >
          {filtered.length === 0 && (
            <li className="px-4 py-3 text-sm text-ink-muted">No matches</li>
          )}
          {filtered.map((cmd, i) => (
            <li
              key={cmd.id}
              id={`cmd-${cmd.id}`}
              role="option"
              aria-selected={i === active}
              onMouseEnter={() => setActive(i)}
              onClick={cmd.run}
              className={`mx-1.5 flex cursor-pointer items-center justify-between px-3 py-2 text-sm ${
                i === active ? 'bg-accent-soft text-ink' : 'text-ink-muted'
              }`}
            >
              <span>{cmd.label}</span>
              <span className="mono-label">{cmd.hint}</span>
            </li>
          ))}
        </ul>
        <div className="flex items-center justify-between border-t border-line px-4 py-2">
          <span className="mono-label">Up and down to move, Enter to go</span>
        </div>
      </div>
    </div>,
    document.body
  );
};

export default CommandMenu;
