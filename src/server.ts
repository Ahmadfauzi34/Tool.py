import {
  AngularNodeAppEngine,
  createNodeRequestHandler,
  isMainModule,
  writeResponseToNodeResponse,
} from '@angular/ssr/node';
import express from 'express';
import {join} from 'node:path';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {readFile, access} from 'node:fs/promises';

const execFilePromise = promisify(execFile);
const browserDistFolder = join(import.meta.dirname, '../browser');

async function getScannerScript(cwd: string): Promise<string> {
  const toolScript = join(cwd, 'tools/ai_studio_tool/file_scanner.py');
  try {
    await access(toolScript);
    return 'tools/ai_studio_tool/file_scanner.py';
  } catch {
    return 'tools/ai_studio_tool/file_scanner.py';
  }
}

const app = express();
const angularApp = new AngularNodeAppEngine();

app.use(express.json());

// API Endpoints for Python File Scanner & Topology Graph
app.get('/api/python-info', async (req, res) => {
  try {
    const cwd = process.cwd();
    const script = await getScannerScript(cwd);
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
    const script = await getScannerScript(cwd);
    await execFilePromise('python3', [script, 'public/topology.json'], { cwd });
    const jsonContent = await readFile(join(cwd, 'public/topology.json'), 'utf-8');
    res.setHeader('Content-Type', 'application/json');
    res.send(jsonContent);
  } catch (error: unknown) {
    const err = error as Error;
    res.status(500).json({ error: 'Failed to scan topology', details: err.message || String(err) });
  }
});

app.get('/api/impact', async (req, res) => {
  const filePath = (req.query['file'] as string) || 'src/app/app.ts';
  try {
    const cwd = process.cwd();
    const script = await getScannerScript(cwd);
    const { stdout } = await execFilePromise('python3', [script, 'impact', filePath], { cwd });
    res.setHeader('Content-Type', 'application/json');
    res.send(stdout);
  } catch (error: unknown) {
    const err = error as Error;
    res.status(500).json({ error: 'Failed to calculate impact', details: err.message || String(err) });
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
    const script = await getScannerScript(cwd);
    const { stdout } = await execFilePromise('python3', [script, 'outline', filePath], { cwd });
    res.setHeader('Content-Type', 'application/json');
    res.send(stdout);
  } catch (error: unknown) {
    const err = error as Error;
    res.status(500).json({ error: 'Failed to extract outline', details: err.message || String(err) });
  }
});

app.get('/api/brief', async (req, res) => {
  const filePath = req.query['file'] as string;
  const rootPath = (req.query['root'] as string) || '.';
  if (!filePath) {
    res.status(400).json({ error: "Parameter 'file' wajib diisi. Contoh: ?file=src/app/app.ts" });
    return;
  }
  try {
    const cwd = process.cwd();
    const script = await getScannerScript(cwd);
    const { stdout } = await execFilePromise('python3', [script, 'brief', filePath, rootPath], { cwd });
    res.setHeader('Content-Type', 'application/json');
    res.send(stdout);
  } catch (error: unknown) {
    const err = error as Error;
    res.status(500).json({ error: 'Failed to generate file brief', details: err.message || String(err) });
  }
});

app.get('/api/async-detector', async (req, res) => {
  const filePath = req.query['file'] as string;
  const mode = (req.query['mode'] as string) || 'file';
  try {
    const cwd = process.cwd();
    const detectorScript = join(cwd, 'tools/ai_studio_tool/async_waterfall_detector.py');
    let args: string[];
    if (mode === 'scan') {
      args = [detectorScript, 'scan', filePath || '.'];
    } else {
      args = [detectorScript, filePath || 'src/app/app.ts'];
    }
    const { stdout } = await execFilePromise('python3', args, { cwd });
    res.setHeader('Content-Type', 'application/json');
    res.send(stdout);
  } catch (error: unknown) {
    const err = error as Error;
    res.status(500).json({ error: 'Failed to analyze async issues', details: err.message || String(err) });
  }
});

app.get('/api/deopt-checker', async (req, res) => {
  const filePath = req.query['file'] as string;
  const mode = (req.query['mode'] as string) || 'file';
  try {
    const cwd = process.cwd();
    const checkerScript = join(cwd, 'tools/ai_studio_tool/deopt_checker.py');
    let args: string[];
    if (mode === 'scan') {
      args = [checkerScript, 'scan', filePath || '.'];
    } else {
      args = [checkerScript, filePath || 'src/app/app.ts'];
    }
    const { stdout } = await execFilePromise('python3', args, { cwd });
    res.setHeader('Content-Type', 'application/json');
    res.send(stdout);
  } catch (error: unknown) {
    const err = error as Error;
    res.status(500).json({ error: 'Failed to check deopt patterns', details: err.message || String(err) });
  }
});

app.get('/api/gc-pressure', async (req, res) => {
  const filePath = req.query['file'] as string;
  const mode = (req.query['mode'] as string) || 'file';
  try {
    const cwd = process.cwd();
    const analyzerScript = join(cwd, 'tools/ai_studio_tool/gc_pressure_analyzer.py');
    let args: string[];
    if (mode === 'scan') {
      args = [analyzerScript, 'scan', filePath || '.'];
    } else {
      args = [analyzerScript, filePath || 'src/app/app.ts'];
    }
    const { stdout } = await execFilePromise('python3', args, { cwd });
    res.setHeader('Content-Type', 'application/json');
    res.send(stdout);
  } catch (error: unknown) {
    const err = error as Error;
    res.status(500).json({ error: 'Failed to analyze GC pressure', details: err.message || String(err) });
  }
});

app.get('/api/cache-auditor', async (req, res) => {
  const filePath = req.query['file'] as string;
  const mode = (req.query['mode'] as string) || 'file';
  try {
    const cwd = process.cwd();
    const auditorScript = join(cwd, 'tools/ai_studio_tool/cache_auditor.py');
    let args: string[];
    if (mode === 'scan') {
      args = [auditorScript, 'scan', filePath || '.'];
    } else {
      args = [auditorScript, filePath || 'src/app/app.ts'];
    }
    const { stdout } = await execFilePromise('python3', args, { cwd });
    res.setHeader('Content-Type', 'application/json');
    res.send(stdout);
  } catch (error: unknown) {
    const err = error as Error;
    res.status(500).json({ error: 'Failed to audit cache patterns', details: err.message || String(err) });
  }
});

app.get('/api/type-isomorphism', async (req, res) => {
  const filePath = req.query['file'] as string;
  const mode = (req.query['mode'] as string) || 'file';
  try {
    const cwd = process.cwd();
    const observerScript = join(cwd, 'tools/ai_studio_tool/type_isomorphism_observer.py');
    let args: string[];
    if (mode === 'scan') {
      args = [observerScript, 'scan', filePath || '.'];
    } else {
      args = [observerScript, filePath || 'src/app/app.ts'];
    }
    const { stdout } = await execFilePromise('python3', args, { cwd });
    res.setHeader('Content-Type', 'application/json');
    res.send(stdout);
  } catch (error: unknown) {
    const err = error as Error;
    res.status(500).json({ error: 'Failed to observe type isomorphisms', details: err.message || String(err) });
  }
});

app.get('/api/boundary-sheaf', async (req, res) => {
  const rootPath = (req.query['root'] as string) || 'src';
  try {
    const cwd = process.cwd();
    const sheafScript = join(cwd, 'tools/ai_studio_tool/boundary_sheaf_checker.py');
    const { stdout } = await execFilePromise('python3', [sheafScript, rootPath], { cwd });
    res.setHeader('Content-Type', 'application/json');
    res.send(stdout);
  } catch (error: unknown) {
    const err = error as Error;
    res.status(500).json({ error: 'Failed to observe boundary sheaf obstructions', details: err.message || String(err) });
  }
});

app.get('/api/homotopy-paths', async (req, res) => {
  const rootPath = (req.query['root'] as string) || 'src';
  try {
    const cwd = process.cwd();
    const scriptPath = join(cwd, 'tools/ai_studio_tool/homotopy_path_observer.py');
    const { stdout } = await execFilePromise('python3', [scriptPath, rootPath], { cwd });
    res.setHeader('Content-Type', 'application/json');
    res.send(stdout);
  } catch (error: unknown) {
    const err = error as Error;
    res.status(500).json({ error: 'Failed to observe homotopy paths', details: err.message || String(err) });
  }
});

app.get('/api/topological-integrity', async (req, res) => {
  const rootPath = (req.query['root'] as string) || 'src';
  try {
    const cwd = process.cwd();
    const scriptPath = join(cwd, 'tools/ai_studio_tool/topological_integrity_orchestrator.py');
    const { stdout } = await execFilePromise('python3', [scriptPath, rootPath], { cwd });
    res.setHeader('Content-Type', 'application/json');
    res.send(stdout);
  } catch (error: unknown) {
    const err = error as Error;
    res.status(500).json({ error: 'Failed to synthesize topological integrity', details: err.message || String(err) });
  }
});

app.get('/api/topological-manifold', async (req, res) => {
  const rootPath = (req.query['root'] as string) || 'src';
  try {
    const cwd = process.cwd();
    const scriptPath = join(cwd, 'tools/ai_studio_tool/topological_manifold_builder.py');
    const { stdout } = await execFilePromise('python3', [scriptPath, rootPath], { cwd });
    res.setHeader('Content-Type', 'application/json');
    res.send(stdout);
  } catch (error: unknown) {
    const err = error as Error;
    res.status(500).json({ error: 'Failed to build topological manifold', details: err.message || String(err) });
  }
});

app.get('/api/topological-fingerprint', async (req, res) => {
  const rootPath = (req.query['root'] as string) || 'src';
  try {
    const cwd = process.cwd();
    const scriptPath = join(cwd, 'tools/ai_studio_tool/invariant_encoder.py');
    const { stdout } = await execFilePromise('python3', [scriptPath, rootPath], { cwd });
    res.setHeader('Content-Type', 'application/json');
    res.send(stdout);
  } catch (error: unknown) {
    const err = error as Error;
    res.status(500).json({ error: 'Failed to encode topological invariants', details: err.message || String(err) });
  }
});

app.get('/api/decoder-steering', async (req, res) => {
  const mode = (req.query['mode'] as string) || 'steer';
  const rootPath = (req.query['root'] as string) || 'src';
  try {
    const cwd = process.cwd();
    const scriptPath = join(cwd, 'tools/ai_studio_tool/decoder_steering.py');
    const { stdout } = await execFilePromise('python3', [scriptPath, mode, rootPath], { cwd });
    res.setHeader('Content-Type', 'application/json');
    res.send(stdout);
  } catch (error: unknown) {
    const err = error as Error;
    res.status(500).json({ error: 'Failed to execute decoder steering', details: err.message || String(err) });
  }
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
