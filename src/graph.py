import heapq
from typing import Dict, List, Tuple, Optional


class FabGraph:
    """
    FAB 내 설비 간 이동 그래프.
    노드: 설비 위치 + LOAD_PORT + BUFFER
    엣지: 양방향 이동 경로 (거리 단위)
    """

    def __init__(self):
        self._adj: Dict[str, List[Tuple[str, float]]] = {}
        self._build_graph()

    def _add_edge(self, u: str, v: str, w: float):
        self._adj.setdefault(u, []).append((v, w))
        self._adj.setdefault(v, []).append((u, w))

    def _build_graph(self):
        """
        FAB 레이아웃 (단순화된 OHT 레일망):

          LOAD_PORT
              |
           BUFFER_A ── ETCH-01 ── ETCH-02
              |
           BUFFER_B ── PHOTO-01 ── PHOTO-02
              |
           BUFFER_C ── CMP-01 ── CMP-02
              |
           UNLOAD_PORT
        """
        edges = [
            ("LOAD_PORT",    "BUFFER_A",   2.0),
            ("BUFFER_A",     "ETCH-01",    1.5),
            ("BUFFER_A",     "ETCH-02",    2.0),
            ("ETCH-01",      "ETCH-02",    1.0),
            ("BUFFER_A",     "BUFFER_B",   3.0),
            ("BUFFER_B",     "PHOTO-01",   1.5),
            ("BUFFER_B",     "PHOTO-02",   2.0),
            ("PHOTO-01",     "PHOTO-02",   1.0),
            ("BUFFER_B",     "BUFFER_C",   3.0),
            ("BUFFER_C",     "CMP-01",     1.5),
            ("BUFFER_C",     "CMP-02",     2.0),
            ("CMP-01",       "CMP-02",     1.0),
            ("BUFFER_C",     "UNLOAD_PORT",2.0),
        ]
        for u, v, w in edges:
            self._add_edge(u, v, w)

    def nodes(self) -> List[str]:
        return list(self._adj.keys())

    def dijkstra(self, source: str) -> Tuple[Dict[str, float], Dict[str, Optional[str]]]:
        """
        단일 출발지 최단 경로 (Dijkstra).
        Returns:
            dist  : {node: shortest_distance}
            prev  : {node: previous_node}
        """
        dist: Dict[str, float] = {n: float("inf") for n in self._adj}
        prev: Dict[str, Optional[str]] = {n: None for n in self._adj}
        dist[source] = 0.0
        heap = [(0.0, source)]

        while heap:
            d, u = heapq.heappop(heap)
            if d > dist[u]:
                continue
            for v, w in self._adj.get(u, []):
                nd = dist[u] + w
                if nd < dist[v]:
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(heap, (nd, v))

        return dist, prev

    def shortest_path(self, source: str, target: str) -> Tuple[float, List[str]]:
        """
        source → target 최단 거리와 경로 반환.
        """
        dist, prev = self.dijkstra(source)
        if dist[target] == float("inf"):
            return float("inf"), []

        path = []
        cur = target
        while cur is not None:
            path.append(cur)
            cur = prev[cur]
        path.reverse()
        return dist[target], path

    def distance(self, source: str, target: str) -> float:
        d, _ = self.shortest_path(source, target)
        return d

    def print_graph(self):
        print("\n=== FAB Graph (adjacency list) ===")
        for node, neighbors in sorted(self._adj.items()):
            edges = ", ".join(f"{v}({w})" for v, w in neighbors)
            print(f"  {node:20s} -> {edges}")
        print()
