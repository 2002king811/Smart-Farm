import { execFileSync, execSync } from 'node:child_process';
import path from 'node:path';

/** Runs a Django management command for the tests: locally with the backend's Python, or on
 * staging through E2E_MANAGE (e.g. "ssh deploy@staging docker compose -f docker-compose.prod.yml
 * exec -T api python manage.py"). */
export function manage(...args: string[]) {
  if (process.env.E2E_MANAGE) {
    execSync(`${process.env.E2E_MANAGE} ${args.map((a) => `'${a}'`).join(' ')}`, { stdio: 'pipe' });
    return;
  }
  const backend = path.resolve(process.cwd(), '../backend');
  const python = process.env.BACKEND_PYTHON ?? path.join(backend, '.venv/bin/python');
  execFileSync(python, ['manage.py', ...args], { cwd: backend, env: process.env, stdio: 'pipe' });
}
