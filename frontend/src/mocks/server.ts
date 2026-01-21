/**
 * MSW server for Vitest (Node.js environment).
 */

import { setupServer } from 'msw/node';
import { handlers } from './handlers';

export const server = setupServer(...handlers);
