import { describe, expect, it } from 'vitest';
import { emptyInput } from '../../src/easy/contracts';
import { productGoal, productSource, validateLiveInput } from '../../src/easy/live-input';

describe('live input retains scientific intent within the Product API bound', () => {
  it('rejects source forms the native API cannot represent without changing identity', () => {
    expect(validateLiveInput({ ...emptyInput(), type: 'uniprot', text: 'P00698-2' })).toContain(
      'isoform',
    );
    expect(validateLiveInput({ ...emptyInput(), type: 'pdb-id', text: 'pdb_00001ubq' })).toContain(
      '扩展 PDB ID',
    );
  });
  it('accepts the exact description bound but blocks a longer description before dispatch', () => {
    expect(validateLiveInput({ ...emptyInput(), text: 'x'.repeat(1500) })).toBeNull();
    expect(validateLiveInput({ ...emptyInput(), text: 'x'.repeat(1501) })).toContain('1,500');
  });
  it('never truncates sequence input, including its final residues', () => {
    const input = { ...emptyInput(), type: 'sequence' as const, text: 'A'.repeat(19999) + 'W' };
    expect(productGoal(input)).toContain(input.text);
    expect(validateLiveInput(input)).toContain('尚未接入');
  });
  it('normalizes an uploaded FASTA into the same explicit sequence source', () => {
    const input = {
      ...emptyInput(),
      type: 'sequence' as const,
      text: '>target\nacde\nfghik',
      file: { name: 'target.fasta', size: 20 },
    };
    expect(productSource(input)).toBeUndefined();
    expect(validateLiveInput(input)).toContain('尚未接入');
  });
  it('includes the entire identifier and organism in the request limit', () => {
    const input = {
      ...emptyInput(),
      type: 'pdb-id' as const,
      text: '1UBQ',
      goal: 'x'.repeat(1500),
    };
    expect(validateLiveInput(input)).toContain('1,500');
    expect(productGoal(input)).toContain('Input pdb-id: 1UBQ.');
  });
});
