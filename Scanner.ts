/** TypeScript facade for tools/scanner. No duplicate Scanner implementation.
 * Read-only matching/change preview are safe for Audit Discovery.
 * scan_edit_write is an effectful Build-only operation and requires authorization.
 * The Python CLI reads one JSON request from stdin and returns one JSON response.
 */
declare const require: (name: string) => unknown;
const childProcess = require('node:child_process') as {
  spawnSync(command: string, args: string[], options: {
    cwd: string; encoding: 'utf8'; input: string; shell: false;
    timeout: number; maxBuffer: number;
  }): { status: number | null; stdout: string; stderr: string; error?: Error };
};

export interface ScanRule {
  name: string;
  pattern: string;
  replacement: string;
  regex?: boolean;
}

export interface ScanChange {
  path: string;
  before_sha256: string;
  after_sha256: string;
  after_content: string;
  matches: Record<string, unknown>[];
  diff: string;
}

export interface ScannerOptions {
  repoRoot: string;
  pythonExecutable?: string;
}

export class Scanner {
  private readonly root: string;
  private readonly python: string;

  constructor(options: ScannerOptions) {
    if (!options.repoRoot) throw new Error('repoRoot is required');
    this.root = options.repoRoot;
    this.python = options.pythonExecutable ?? 'python';
  }

  private invoke<T>(operation: string, payload: Record<string, unknown>, apply = false): T {
    const args = ['-m', 'tools.scanner', operation, '--repo-root', this.root];
    if (apply) args.push('--apply');
    const proc = childProcess.spawnSync(this.python, args, {
      cwd: this.root,
      encoding: 'utf8',
      input: JSON.stringify(payload),
      shell: false,
      timeout: 30000,
      maxBuffer: 32 * 1024 * 1024,
    });
    if (proc.error) throw proc.error;
    if (proc.status !== 0) throw new Error(`Scanner ${operation} failed: ${proc.stderr}`);
    const response = JSON.parse(proc.stdout) as { ok: boolean; result: T; error?: string };
    if (!response.ok) throw new Error(response.error ?? 'Scanner failed');
    return response.result;
  }

  scan_match_variable(rules: ScanRule[], paths?: string[]) {
    return this.invoke<{ matches: Record<string, unknown>[]; count: number }>(
      'match', { rules, paths },
    );
  }

  scan_edit_change(rules: ScanRule[], paths?: string[]) {
    return this.invoke<{ changes: ScanChange[]; count: number }>(
      'change', { rules, paths },
    );
  }

  scan_edit_write(changes: ScanChange[], allowedPaths: string[], authorized = false) {
    if (!authorized) throw new Error('Build authorization required for scanner write');
    return this.invoke<{ written: { path: string; sha256: string }[]; count: number }>(
      'write', { changes, allowed_paths: allowedPaths }, true,
    );
  }

  scan_filesystems(includeUntracked = false) {
    return this.invoke<{ files: Record<string, unknown>[]; count: number }>(
      'filesystems', { include_untracked: includeUntracked },
    );
  }
}
