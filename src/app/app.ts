import { ChangeDetectionStrategy, Component, computed, signal, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';

export interface TopologyNode {
  id: string;
  path: string;
  label: string;
  type: 'Service' | 'Component' | 'Module' | 'Helper' | 'Other';
}

export interface TopologyEdge {
  source: string;
  target: string;
}

export interface Topology {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  save_error?: string;
}

export interface ImpactResult {
  target: string;
  upstream: string[];
  downstream: string[];
  circular_references: string[];
}

export interface PythonInfo {
  supported: boolean;
  runtime: string;
  version: string;
  script: string;
  status: string;
  error?: string;
}

@Component({
  changeDetection: ChangeDetectionStrategy.OnPush,
  selector: 'app-root',
  imports: [CommonModule, FormsModule, MatIconModule],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App implements OnInit {
  pythonInfo = signal<PythonInfo | null>(null);
  topology = signal<Topology | null>(null);
  loading = signal<boolean>(true);
  scanning = signal<boolean>(false);
  
  selectedFile = signal<string>('src/app/app.ts');
  impactResult = signal<ImpactResult | null>(null);
  impactLoading = signal<boolean>(false);
  
  filterType = signal<string>('ALL');
  searchQuery = signal<string>('');
  activeTab = signal<'topology' | 'impact' | 'python' | 'protocol'>('topology');
  selectedNode = signal<TopologyNode | null>(null);
  copiedMessage = signal<string | null>(null);

  // Computed properties
  nodeStats = computed(() => {
    const topo = this.topology();
    if (!topo) return { total: 0, services: 0, components: 0, modules: 0, helpers: 0, others: 0, edges: 0 };
    const nodes = topo.nodes || [];
    return {
      total: nodes.length,
      services: nodes.filter(n => n.type === 'Service').length,
      components: nodes.filter(n => n.type === 'Component').length,
      modules: nodes.filter(n => n.type === 'Module').length,
      helpers: nodes.filter(n => n.type === 'Helper').length,
      others: nodes.filter(n => n.type === 'Other').length,
      edges: (topo.edges || []).length
    };
  });

  filteredNodes = computed(() => {
    const topo = this.topology();
    if (!topo) return [];
    let nodes = topo.nodes || [];
    const filter = this.filterType();
    const query = this.searchQuery().toLowerCase().trim();

    if (filter !== 'ALL') {
      nodes = nodes.filter(n => n.type === filter);
    }

    if (query) {
      nodes = nodes.filter(n => 
        n.path.toLowerCase().includes(query) || 
        n.label.toLowerCase().includes(query) ||
        n.type.toLowerCase().includes(query)
      );
    }

    return nodes;
  });

  ngOnInit() {
    this.checkPythonInfo();
    this.loadTopology();
  }

  async checkPythonInfo() {
    try {
      const res = await fetch('/api/python-info');
      const data = await res.json();
      this.pythonInfo.set(data);
    } catch (e: unknown) {
      const err = e as Error;
      this.pythonInfo.set({
        supported: false,
        runtime: 'Python 3',
        version: 'Unknown',
        script: 'file_scanner.py',
        status: 'error',
        error: err.message || String(err)
      });
    }
  }

  async loadTopology() {
    this.loading.set(true);
    try {
      const res = await fetch('/api/topology');
      if (!res.ok) throw new Error('Failed to fetch topology');
      const data = await res.json();
      this.topology.set(data);
      if (data.nodes && data.nodes.length > 0) {
        const appTsNode = data.nodes.find((n: TopologyNode) => n.path === 'src/app/app.ts');
        this.selectedNode.set(appTsNode || data.nodes[0]);
        this.selectedFile.set(appTsNode ? appTsNode.path : data.nodes[0].path);
        this.analyzeImpact(this.selectedFile());
      }
    } catch (e: unknown) {
      console.error(e);
    } finally {
      this.loading.set(false);
    }
  }

  async triggerReScan() {
    this.scanning.set(true);
    try {
      await this.loadTopology();
      if (this.selectedFile()) {
        await this.analyzeImpact(this.selectedFile());
      }
      this.showToast('Codebase Topology scanned & updated via Python!');
    } catch (e: unknown) {
      const err = e as Error;
      this.showToast('Scan error: ' + (err.message || String(err)));
    } finally {
      this.scanning.set(false);
    }
  }

  async analyzeImpact(filePath: string) {
    if (!filePath) return;
    this.impactLoading.set(true);
    try {
      const res = await fetch(`/api/impact?file=${encodeURIComponent(filePath)}`);
      if (!res.ok) throw new Error('Failed to compute impact');
      const data = await res.json();
      this.impactResult.set(data);
    } catch (e: unknown) {
      console.error(e);
    } finally {
      this.impactLoading.set(false);
    }
  }

  selectNode(node: TopologyNode) {
    this.selectedNode.set(node);
    this.selectedFile.set(node.path);
    this.analyzeImpact(node.path);
  }

  setTab(tab: 'topology' | 'impact' | 'python' | 'protocol') {
    this.activeTab.set(tab);
  }

  setFilter(type: string) {
    this.filterType.set(type);
  }

  updateSearch(event: Event) {
    const value = (event.target as HTMLInputElement).value;
    this.searchQuery.set(value);
  }

  onFileSelectChange(event: Event) {
    const val = (event.target as HTMLSelectElement).value;
    this.selectedFile.set(val);
    const node = this.topology()?.nodes.find(n => n.path === val);
    if (node) this.selectedNode.set(node);
    this.analyzeImpact(val);
  }

  copyToClipboard(text: string, label: string) {
    navigator.clipboard.writeText(text);
    this.showToast(`${label} copied to clipboard!`);
  }

  showToast(msg: string) {
    this.copiedMessage.set(msg);
    setTimeout(() => {
      this.copiedMessage.set(null);
    }, 3000);
  }

  getNodeBadge(type: string): string {
    switch (type) {
      case 'Service':
        return 'bg-emerald-600 text-white';
      case 'Component':
        return 'bg-sky-600 text-white';
      case 'Module':
        return 'bg-purple-600 text-white';
      case 'Helper':
        return 'bg-amber-600 text-white';
      default:
        return 'bg-slate-600 text-white';
    }
  }

  getNodeImports(path: string): string[] {
    const topo = this.topology();
    if (!topo || !topo.edges) return [];
    return topo.edges.filter(e => e.source === path).map(e => e.target);
  }

  getNodeImportedBy(path: string): string[] {
    const topo = this.topology();
    if (!topo || !topo.edges) return [];
    return topo.edges.filter(e => e.target === path).map(e => e.source);
  }
}
