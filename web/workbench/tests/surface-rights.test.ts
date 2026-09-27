import { describe, expect, it } from 'vitest';
import {surfaceRights} from '../../shared/account-client';

describe('surface rights gating matrix', () => {
  it('keeps the legacy single-user surface fully enabled', () => {
    expect(surfaceRights(undefined)).toEqual({
      canEdit: true, canExecute: true, canDiscuss: true, readOnly: false,
    });
  });
  it('lets team members co-edit and discuss but not launch or approve', () => {
    expect(surfaceRights({can_edit: true, can_execute: false, role: 'member'})).toEqual({
      canEdit: true, canExecute: false, canDiscuss: true, readOnly: false,
    });
  });
  it('treats read-only admin observation as fully read-only', () => {
    expect(surfaceRights({can_edit: false, can_execute: false, role: 'observer'})).toEqual({
      canEdit: false, canExecute: false, canDiscuss: false, readOnly: true,
    });
  });
  it('keeps owners and team admins as the scientific approvers', () => {
    for (const role of ['owner', 'admin']) {
      expect(surfaceRights({can_edit: true, can_execute: true, role}).canExecute).toBe(true);
    }
  });
  it('removes execution affordances when no scientific launcher is configured', () => {
    // Accounts-only service: co-editing survives, execution and project
    // conversation (backend _admit refuses without a launcher) do not.
    const owner = surfaceRights({can_edit: true, can_execute: true, role: 'owner'}, false);
    expect(owner).toEqual({canEdit: true, canExecute: false, canDiscuss: false, readOnly: false});
    const member = surfaceRights({can_edit: true, can_execute: false, role: 'member'}, false);
    expect(member.canEdit).toBe(true);
    expect(member.canExecute).toBe(false);
    const observer = surfaceRights({can_edit: false, can_execute: false, role: 'observer'}, false);
    expect(observer.readOnly).toBe(true);
  });
});
