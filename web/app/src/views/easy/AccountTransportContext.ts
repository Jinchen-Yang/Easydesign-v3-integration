import {createContext} from 'react';
import type {AccountScope} from '../../shared/account-client';

export const AccountTransportContext = createContext<{
  transport: typeof fetch; scope: AccountScope;
} | null>(null);
