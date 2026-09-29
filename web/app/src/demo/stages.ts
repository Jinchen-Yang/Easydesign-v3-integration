import type { WorkflowPhase } from '../adapters/WorkbenchAdapter';
export interface StageEvent {
  title: string;
  text: string;
  detail: string;
}
export interface StageContent {
  title: string;
  summary: string;
  subtasks: string[];
  specialists: [string, string][];
  events: StageEvent[];
}
export const stages: Record<WorkflowPhase, StageContent> = {
  goal: {
    title: 'A focused starting point',
    summary:
      'We’ll explore a compact, accessible epitope on lysozyme, then compare two VHH design approaches. This guided demo ends with a six-candidate panel. All design results are simulated.',
    subtasks: ['Understand the research goal', 'Define the demo scope', 'Prepare the workflow'],
    specialists: [['Design Scientist', 'Research coordination']],
    events: [
      {
        title: 'Research goal captured',
        text: 'Lysozyme target · VHH binder',
        detail: 'Your original goal is preserved throughout this demo.',
      },
      {
        title: 'Workflow prepared',
        text: 'Six research steps, with you at each decision',
        detail:
          'This demo uses fixed reference data and simulated outputs. No model or compute job runs.',
      },
    ],
  },
  target: {
    title: 'Meet your target',
    summary:
      'Hen egg-white lysozyme is ready for review. We’re using PDB 1MEL as a reference, showing target chain L (label C) on its own. Confirm the target before we compare possible binding sites.',
    subtasks: [
      'Parse target request',
      'Load reference structure',
      'Resolve target chain',
      'Prepare structure context',
    ],
    specialists: [
      ['Target Intelligence', 'Identity & reference'],
      ['Structure Analyst', 'Chain & sequence'],
      ['Evidence Judge', 'Reference review'],
    ],
    events: [
      {
        title: 'Target Intelligence',
        text: 'Lysozyme identified in the demo reference',
        detail:
          'Hen egg-white lysozyme · UniProt P00698. This is the fixed target for the prototype.',
      },
      {
        title: 'Structure metadata loaded',
        text: '1MEL · target L / label C · VHH A',
        detail:
          'The bundled PDB contains lysozyme author chains L/M (mmCIF labels C/D) and VHH chains A/B. The viewer checks L/A against the loaded file.',
      },
      {
        title: 'Reference structure ready',
        text: 'Target-only view prepared',
        detail:
          'The public 1MEL complex is a visualization reference, not a generated EasyDesign prediction.',
      },
    ],
  },
  site: {
    title: 'Three sites. One clear next step.',
    summary:
      'Three candidate sites are ready for comparison. Site B gives the clearest accessible surface in this demo. Select a site to explore its residues, or compare all three before approving.',
    subtasks: [
      'Inspect target surface',
      'Generate A/B/C candidates',
      'Compare demo accessibility',
      'Select a site to approve',
    ],
    specialists: [
      ['Structure Analyst', 'Surface context'],
      ['Site Strategist', 'Site comparison'],
      ['Evidence Judge', 'Demo evidence review'],
    ],
    events: [
      {
        title: 'Surface context prepared',
        text: 'Three distinct residue groups mapped',
        detail:
          'A/B/C residue selections come from the supplied UI fixture. They are not validated epitopes.',
      },
      {
        title: 'Site comparison complete',
        text: 'Accessibility, geometry and evidence compared',
        detail:
          'All three scores are simulated values for interface development. Selecting a site changes the viewer highlight.',
      },
      {
        title: 'Site B recommended',
        text: 'A compact surface to start the pilot',
        detail:
          'High-level demo rationale: B has the highest fixture accessibility and geometry scores. No binding claim is made.',
      },
    ],
  },
  design: {
    title: 'A small, informative first experiment',
    summary:
      'We’ll compare a focused hotspot arm with a broader interface arm, using four candidates each. That gives us an eight-candidate pilot before committing to a larger panel.',
    subtasks: [
      'Confirm approved site',
      'Select VHH scaffold',
      'Define two design arms',
      'Set the pilot budget',
    ],
    specialists: [
      ['Design Strategist', 'Two-arm comparison'],
      ['Evidence Judge', 'Scope review'],
    ],
    events: [
      {
        title: 'Approved site carried forward',
        text: 'Your selected site anchors both arms',
        detail:
          'The approved site is read from adapter state, never inferred from conversation text.',
      },
      {
        title: 'Design arms prepared',
        text: 'Focused hotspot + broader interface',
        detail: 'Each arm contains exactly four simulated candidates.',
      },
      {
        title: 'Pilot plan ready',
        text: '8 candidates · one bounded comparison',
        detail:
          'Approve to play the deterministic pilot. This does not launch scientific software.',
      },
    ],
  },
  pilot: {
    title: 'The pilot is ready to review',
    summary:
      'The simulated pilot produced 6 passing candidates out of 8. Both design arms are represented. Review the candidates on the right, then promote the six passing candidates to the next demo batch.',
    subtasks: [
      'Start the simulated pilot',
      'Generate 8 demo sequences',
      'Complete structure checks',
      'Review 6 pass / 2 filtered',
    ],
    specialists: [
      ['Design Specialist', 'Candidate generation'],
      ['Structure Analyst', 'Simulated evaluation'],
      ['Evidence Judge', 'Pilot summary'],
    ],
    events: [
      {
        title: 'Pilot generation started',
        text: '2 design arms · 4 candidates each',
        detail: 'This event is simulated; no GPU or backend is contacted.',
      },
      {
        title: 'Eight candidates prepared',
        text: 'P-01 through P-08',
        detail: 'Candidate identifiers and scores come from the deterministic fixture.',
      },
      {
        title: 'Structure checks complete',
        text: '6 pass · 2 filtered',
        detail:
          'Pass/filtered outcomes are simulated. All structures reuse the 1MEL reference complex.',
      },
      {
        title: 'Pilot review complete',
        text: 'Six candidates ready to promote',
        detail:
          'Promotion advances the demo only. It does not authorize or run a real scientific job.',
      },
    ],
  },
  scale: {
    title: 'Expanding the comparison',
    summary:
      'The larger demo explores 24 candidates in three batches of eight. We’ll carry six finalists into the final panel after the simulated review.',
    subtasks: [
      'Prepare the 24-candidate demo',
      'Complete batch 1 of 3',
      'Complete batch 2 of 3',
      'Complete batch 3 of 3',
    ],
    specialists: [
      ['Design Specialist', 'Batch preparation'],
      ['Candidate Reviewer', 'Simulated filtering'],
    ],
    events: [
      {
        title: 'Scale demo prepared',
        text: '24 candidates · 3 batches × 8',
        detail: 'The scale budget is fixed at 24 and cannot trigger compute.',
      },
      {
        title: 'Batch 1 completed',
        text: '8 of 24 reviewed',
        detail: '6 passing · 2 filtered. Simulated batch result.',
      },
      {
        title: 'Batch 2 completed',
        text: '16 of 24 reviewed',
        detail: '12 passing · 4 filtered across two batches. Simulated batch result.',
      },
      {
        title: 'Batch 3 completed',
        text: '24 of 24 reviewed · 18 pass',
        detail: '18 passing · 6 filtered. The six finalists are defined by the demo fixture.',
      },
    ],
  },
  candidates: {
    title: 'Your six-candidate panel',
    summary:
      'Six finalists are ready to explore. Select any candidate to inspect its demo metrics and reference complex. Star the ones you want to revisit, then finalize the panel.',
    subtasks: [
      'Review 18 passing candidates',
      'Compare the 6 finalists',
      'Explore the reference complex',
      'Finalize the candidate panel',
    ],
    specialists: [
      ['Candidate Reviewer', 'Panel comparison'],
      ['Design Scientist', 'Final summary'],
    ],
    events: [
      {
        title: 'Finalist panel prepared',
        text: 'ED-001 through ED-006',
        detail:
          'These identifiers, sequences and scores are UI fixtures, not newly designed proteins.',
      },
      {
        title: 'Comparison ready',
        text: '6 finalists · simulated results',
        detail:
          'Every candidate uses the known 1MEL complex as a shared visual placeholder. Selection changes the view and displayed metrics.',
      },
    ],
  },
};
