import React from 'react';
import { Link } from 'react-router-dom';
import { getProjects } from '../../content';
import { listWork, manName, type WorkEntry } from '../../content/caseStudies';
import { loadCaseStudies } from '../../content/loaders';
import { MonoLabel, SectionHeading, Sheet } from '../drawing';

/** One row of the work index, linking to its case study page. */
const WorkRow: React.FC<{ entry: WorkEntry; index: number }> = ({
  entry,
  index,
}) => (
  <li className="border-b border-line">
    <Link
      to={`/work/${entry.slug}`}
      className="group grid gap-2 py-5 transition-colors hover:bg-paper-sunk md:grid-cols-[4rem_minmax(0,16rem)_minmax(0,1fr)_7rem] md:items-baseline md:gap-6 md:px-3 md:-mx-3"
    >
      <span className="font-mono text-xs text-accent tabular-nums">
        W{String(index + 1).padStart(2, '0')}
      </span>
      <span>
        <span className="block text-lg font-semibold tracking-tight text-ink">
          {entry.title}
        </span>
        <span className="block font-mono text-[0.6875rem] text-ink-faint">
          {manName(entry.slug).toLowerCase()}(7)
        </span>
      </span>
      <span>
        <span className="block text-sm leading-relaxed text-ink-muted">
          {entry.summary}
        </span>
        {entry.stack.length > 0 && (
          <span className="mt-2 block font-mono text-xs text-ink-muted">
            <span className="sr-only">Stack: </span>
            {entry.stack.slice(0, 5).join(' / ')}
          </span>
        )}
      </span>
      <span className="mono-label flex items-center gap-2 md:justify-end">
        {entry.hasWriteUp ? 'Write-up' : 'Notes'}
        <span
          aria-hidden="true"
          className="text-ink-muted transition-transform motion-safe:group-hover:translate-x-0.5"
        >
          →
        </span>
      </span>
    </Link>
  </li>
);

/** The work index: case studies first, then the other projects. */
export const Projects: React.FC = () => {
  const work = listWork(loadCaseStudies(), getProjects());

  return (
    <section
      id="work"
      aria-labelledby="work-title"
      className="border-b border-line py-20 sm:py-24"
    >
      <Sheet>
        <SectionHeading
          index="02"
          label="Work"
          id="work-title"
          title="Case studies"
          aside={
            <MonoLabel>
              {String(work.length).padStart(2, '0')} entries
            </MonoLabel>
          }
        >
          What each system does, how it is built and what it taught me.
        </SectionHeading>
        <ul className="border-t border-line">
          {work.map((entry, index) => (
            <WorkRow key={entry.slug} entry={entry} index={index} />
          ))}
        </ul>
      </Sheet>
    </section>
  );
};
