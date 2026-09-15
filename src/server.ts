import {
  AngularNodeAppEngine,
  createNodeRequestHandler,
  isMainModule,
  writeResponseToNodeResponse,
} from '@angular/ssr/node';
import express from 'express';
import {basename, isAbsolute, join, relative, resolve, sep} from 'node:path';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {access} from 'node:fs/promises';

const execFilePromise = promisify(execFile);
const browserDistFolder = join(import.meta.dirname, '../browser');

interface KernelGraph {
  shared_graph?: {
    vertices?: string[];
    edges?: [string, string][];
  };
}

interface KernelImpact {
  target?: string;
  upstream?: string[];
  downstream?: string[];
  circular_references?: string[];
  [key: string]: unknown;
}

class InvalidCorpusTargetError extends Error {}

function getCorpusRoot(): string {
  return resolve(process.env['AI_STUDIO_CORPUS_ROOT'] || process.cwd());
}

async function getKernelScript(cwd: string): Promise<string> {
  const configuredDirectory = process.env['AI_STUDIO_TOOL_DIR'];
  const candidates = [
    configuredDirectory
      ? join(resolve(cwd, configuredDirectory), 'hott_kernel.py')
      : undefined,
    join(cwd, 'tools/ai_studio_tool/hott_kernel.py'),
  ].filter((candidate): candidate is string => Boolean(candidate));

  for (const candidate of candidates) {
    try {
      await access(candidate);
      return candidate;
    } catch {
      // Continue to the next explicit candidate.
    }
  }

  throw new Error(
    `hott_kernel.py not found; set AI_STUDIO_TOOL_DIR to the external ai_studio_tool directory (checked: ${candidates.join(', ')})`,
  );
}

function resolveCorpusTarget(corpusRoot: string, requestedTarget: string): string {
  const target = resolve(corpusRoot, requestedTarget);
  const relativeTarget = relative(corpusRoot, target);
  if (
    relativeTarget === '..' ||
    relativeTarget.startsWith(`..${sep}`) ||
    isAbsolute(relativeTarget)
  ) {
    throw new InvalidCorpusTargetError(
      `Target must stay inside the configured corpus root: ${requestedTarget}`,
    );
  }
  return target;
}

function corpusPath(corpusRoot: string, filePath: string): string {
  const path = relative(corpusRoot, filePath);
  return (path || '.').split(sep).join('/');
}

function classifyNode(path: string): 'Service' | 'Component' | 'Module' | 'Helper' | 'Other' {
  if (/service\.ts$/i.test(path)) return 'Service';
  if (/(component\.ts|(^|\/)app\.ts)$/i.test(path)) return 'Component';
  if (/(module|routes?|config)(\.|\/)/i.test(path)) return 'Module';
  if (/(^|\/)(utils?|helpers?)(\/|$)/i.test(path)) return 'Helper';
  return 'Other';
}

async function runKernel<T>(cwd: string, args: string[]): Promise<T> {
  const script = await getKernelScript(cwd);
  const {stdout} = await execFilePromise('python3', [script, ...args], {
    cwd,
    encoding: 'utf8',
    maxBuffer: 16 * 1024 * 1024,
  });
  return JSON.parse(stdout) as T;
}

function topologyResponse(corpusRoot: string, kernel: KernelGraph) {
  const vertices = kernel.shared_graph?.vertices || [];
  const edges = kernel.shared_graph?.edges || [];
  return {
    nodes: vertices.map((vertex) => {
      const path = corpusPath(corpusRoot, vertex);
      return {
        id: path,
        path,
        label: basename(path),
        type: classifyNode(path),
      };
    }),
    edges: edges.map(([source, target]) => ({
      source: corpusPath(corpusRoot, source),
      target: corpusPath(corpusRoot, target),
    })),
  };
}

function impactResponse(corpusRoot: string, kernel: KernelImpact) {
  const mapPaths = (value: unknown): string[] =>
    Array.isArray(value)
      ? value.filter((item): item is string => typeof item === 'string').map((item) => corpusPath(corpusRoot, item))
      : [];

  const response: KernelImpact = {...kernel};
  const scalarPathKeys = ['target', 'file', 'requested_target'];
  const arrayPathKeys = [
    'upstream',
    'downstream',
    'direct_upstream',
    'direct_downstream',
    'affected_entrypoints',
    'circular_references',
    'candidate_targets',
  ];

  for (const key of scalarPathKeys) {
    const value = response[key];
    if (typeof value === 'string' && isAbsolute(value)) {
      response[key] = corpusPath(corpusRoot, value);
    }
  }
  for (const key of arrayPathKeys) {
    if (key in response) response[key] = mapPaths(response[key]);
  }

  return response;
}

function queryResponse(corpusRoot: string, kernel: Record<string, unknown>) {
  const response = impactResponse(corpusRoot, kernel as KernelImpact);
  if (kernel['impact'] && typeof kernel['impact'] === 'object') {
    response['impact'] = impactResponse(
      corpusRoot,
      kernel['impact'] as KernelImpact,
    );
  }
  return response;
}

const app = express();
const angularApp = new AngularNodeAppEngine();

app.use(express.json());

// API Endpoints for Python File Scanner & Topology Graph
app.get('/api/python-info', async (req, res) => {
  try {
    const cwd = process.cwd();
    const script = await getKernelScript(cwd);
    const { stdout: versionOut } = await execFilePromise('python3', ['--version']);
    res.json({
      supported: true,
      runtime: 'Python 3',
      version: versionOut.trim(),
      script,
      status: 'active'
    });
  } catch (error: unknown) {
    const err = error as Error;
    res.json({
      supported: false,
      error: err.message || String(err)
    });
  }
});

app.get('/api/topology', async (req, res) => {
  try {
    const cwd = process.cwd();
    const corpusRoot = getCorpusRoot();
    const kernel = await runKernel<KernelGraph>(cwd, [
      'analyze', corpusRoot, '--cache-mode', 'off', '--output', 'graph',
    ]);
    res.json(topologyResponse(corpusRoot, kernel));
  } catch (error: unknown) {
    const err = error as Error;
    res.status(500).json({ error: 'Failed to scan topology', details: err.message || String(err) });
  }
});

app.get('/api/impact', async (req, res) => {
  const filePath = (req.query['file'] as string) || 'src/app/app.ts';
  try {
    const cwd = process.cwd();
    const corpusRoot = getCorpusRoot();
    const target = resolveCorpusTarget(corpusRoot, filePath);
    const kernel = await runKernel<KernelImpact>(cwd, [
      'impact', target, corpusRoot, '--cache-mode', 'off', '--output', 'full',
    ]);
    res.json(impactResponse(corpusRoot, kernel));
  } catch (error: unknown) {
    const err = error as Error;
    const status = err instanceof InvalidCorpusTargetError ? 400 : 500;
    res.status(status).json({ error: 'Failed to calculate impact', details: err.message || String(err) });
  }
});

app.get('/api/outline', async (req, res) => {
  const filePath = req.query['file'] as string;
  if (!filePath) {
    res.status(400).json({ error: "Parameter 'file' wajib diisi. Contoh: ?file=src/app/app.ts" });
    return;
  }
  try {
    const cwd = process.cwd();
    const corpusRoot = getCorpusRoot();
    const target = resolveCorpusTarget(corpusRoot, filePath);
    const kernel = await runKernel<Record<string, unknown>>(cwd, [
      'outline', target, corpusRoot, '--cache-mode', 'off', '--output', 'full',
    ]);
    res.json(queryResponse(corpusRoot, kernel));
  } catch (error: unknown) {
    const err = error as Error;
    const status = err instanceof InvalidCorpusTargetError ? 400 : 500;
    res.status(status).json({ error: 'Failed to extract outline', details: err.message || String(err) });
  }
});

app.get('/api/brief', async (req, res) => {
  const filePath = req.query['file'] as string;
  if (!filePath) {
    res.status(400).json({ error: "Parameter 'file' wajib diisi. Contoh: ?file=src/app/app.ts" });
    return;
  }
  try {
    const cwd = process.cwd();
    const corpusRoot = getCorpusRoot();
    const target = resolveCorpusTarget(corpusRoot, filePath);
    const kernel = await runKernel<Record<string, unknown>>(cwd, [
      'brief', target, corpusRoot, '--cache-mode', 'off', '--output', 'full',
    ]);
    res.json(queryResponse(corpusRoot, kernel));
  } catch (error: unknown) {
    const err = error as Error;
    const status = err instanceof InvalidCorpusTargetError ? 400 : 500;
    res.status(status).json({ error: 'Failed to generate file brief', details: err.message || String(err) });
  }
});

const retiredEndpoints = [
  '/api/async-detector',
  '/api/deopt-checker',
  '/api/gc-pressure',
  '/api/cache-auditor',
  '/api/type-isomorphism',
  '/api/boundary-sheaf',
  '/api/homotopy-paths',
  '/api/topological-integrity',
  '/api/topological-manifold',
  '/api/topological-fingerprint',
  '/api/decoder-steering',
];

app.get(retiredEndpoints, (_req, res) => {
  res.status(410).json({
    error: 'This legacy standalone analyzer endpoint has been retired.',
    replacements: ['/api/topology', '/api/impact', '/api/outline', '/api/brief'],
  });
});

/**
 * Serve static files from /browser
 */
app.use(
  express.static(browserDistFolder, {
    maxAge: '1y',
    index: false,
    redirect: false,
  }),
);

/**
 * Handle all other requests by rendering the Angular application.
 */
app.use((req, res, next) => {
  angularApp
    .handle(req)
    .then((response) =>
      response ? writeResponseToNodeResponse(response, res) : next(),
    )
    .catch(next);
});

/**
 * Start the server if this module is the main entry point, or it is ran via PM2.
 * The server listens on the port defined by the `PORT` environment variable, or defaults to 4000.
 */
if (isMainModule(import.meta.url) || process.env['pm_id']) {
  const port = process.env['PORT'] || 4000;
  app.listen(port, (error) => {
    if (error) {
      throw error;
    }

    console.log(`Node Express server listening on http://localhost:${port}`);
  });
}

/**
 * Request handler used by the Angular CLI (for dev-server and during build) or Firebase Cloud Functions.
 */
export const reqHandler = createNodeRequestHandler(app);
