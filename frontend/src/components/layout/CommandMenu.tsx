import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useLocation, useNavigate } from 'react-router-dom';
import type { NavigationItem } from '../../types';
import { getPublishedPosts, getSiteContent } from '../../content';
import { listCaseStudies } from '../../content/caseStudies';
import { loadCaseStudies } from '../../content/loaders';
import { MAP_NODES } from '../../content/map';
import { buildCommands, filterCommands, type PaletteCommand } from './commands';

/** Props for {@link CommandMenu}. */
interface CommandMenuProps {
  open: boolean;
  onClose: () => void;
  items: NavigationItem[];
  onToggleTheme: () => void;
}

/** The resume link, falling back to the PDF served with the site. */
const resumeUrl = (): string => getSiteContent().resume_url || '/Profile.pdf';

/**
 * The command menu opened by the header button or Cmd+K.
 *
 * It jumps to a node on the system map, a case study, a post, a page, the
 * resume or the contact section, and switches the theme. Typing filters and
 * ranks the rows, arrow keys move, Enter runs, Escape closes and focus returns
 * to whatever opened it.
 */
export const CommandMenu: React.FC<CommandMenuProps> = ({
  open,
  onClose,
  items,
  onToggleTheme,
}) => {
  const navigate = useNavigate();
  const location = useLocation();
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);

  const commands = useMemo(
    () =>
      buildCommands({
        nodes: MAP_NODES,
        caseStudies: listCaseStudies(loadCaseStudies()),
        posts: getPublishedPosts(),
        navigation: items,
        resumeUrl: resumeUrl(),
      }),
    [items]
  );

  const filtered = useMemo(
    () => filterCommands(commands, query),
    [commands, query]
  );
  const grouped = query.trim() === '';

  const run = (command: PaletteCommand) => {
    onClose();
    const { target } = command;
    if (target.kind === 'theme') {
      onToggleTheme();
    } else if (target.kind === 'file') {
      window.open(target.href, '_blank', 'noopener,noreferrer');
    } else if (target.kind === 'anchor') {
      if (location.pathname === '/') {
        document.getElementById(target.id)?.scrollIntoView();
        window.history.replaceState(window.history.state, '', `#${target.id}`);
      } else {
        window.location.assign(`/#${target.id}`);
      }
    } else if (target.focusNode) {
      void navigate(target.to, { state: { focusNode: target.focusNode } });
    } else {
      void navigate(target.to);
    }
  };

  useEffect(() => {
    if (!open) return;
    returnFocus.current = document.activeElement as HTMLElement | null;
    setQuery('');
    setActive(0);
    inputRef.current?.focus();
    return () => returnFocus.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    listRef.current
      ?.querySelector(`#cmd-${active}`)
      ?.scrollIntoView?.({ block: 'nearest' });
  }, [active, open]);

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
      const command = filtered[active];
      if (command) run(command);
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
        className="absolute inset-0 bg-paper/80"
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
            placeholder="Search the site"
            aria-label="Search the site"
            aria-controls="command-menu-list"
            aria-activedescendant={
              filtered[active] ? `cmd-${active}` : undefined
            }
            role="combobox"
            aria-expanded="true"
            className="h-12 w-full bg-transparent text-sm text-ink placeholder:text-ink-faint focus:outline-none"
          />
          <kbd className="mono-label border border-line px-1.5 py-0.5">Esc</kbd>
        </div>
        <ul
          ref={listRef}
          id="command-menu-list"
          role="listbox"
          aria-label="Destinations"
          className="max-h-96 overflow-y-auto py-1.5 scrollbar-thin"
        >
          {filtered.length === 0 && (
            <li
              role="presentation"
              className="px-4 py-3 text-sm text-ink-muted"
            >
              No matches
            </li>
          )}
          {filtered.map((cmd, i) => {
            const heading =
              grouped && cmd.group !== filtered[i - 1]?.group
                ? cmd.group
                : null;
            return (
              <React.Fragment key={cmd.id}>
                {heading && (
                  <li
                    role="presentation"
                    className="mono-label px-4 pb-1 pt-3 first:pt-1.5"
                  >
                    {heading}
                  </li>
                )}
                <li
                  id={`cmd-${i}`}
                  role="option"
                  aria-selected={i === active}
                  onMouseMove={() => setActive(i)}
                  onClick={() => run(cmd)}
                  className={`mx-1.5 flex cursor-pointer items-center justify-between gap-4 px-3 py-2 text-sm ${
                    i === active ? 'bg-accent-soft text-ink' : 'text-ink-muted'
                  }`}
                >
                  <span className="min-w-0 break-words">{cmd.label}</span>
                  <span className="mono-label shrink-0">
                    {grouped ? cmd.hint : cmd.group}
                  </span>
                </li>
              </React.Fragment>
            );
          })}
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
