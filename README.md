# FAB AMHS Simulator

반도체 FAB의 **AMHS(Automated Material Handling System)** 핵심 로직을 Python 콘솔 시뮬레이터로 구현한 포트폴리오 프로젝트입니다.  
Scheduling, Route Finding, Failover 세 가지 핵심 개념을 실제 동작 코드로 검증합니다.

---

## 프로젝트 개요

| 항목 | 내용 |
|---|---|
| 목적 | SK하이닉스 AMHS 직무 지원 포트폴리오 |
| 언어 | Python 3.8+ (외부 라이브러리 없음) |
| 주요 모듈 | `heapq`, `dataclasses`, `random`, `logging` |
| 시뮬레이션 방식 | Tick 기반 이산 사건 시뮬레이션 |

### 구현 범위

```
설비 6대   ETCH-01/02 · PHOTO-01/02 · CMP-01/02
OHT  3대   OHT-01 · OHT-02 · OHT-03
LOT  3개   LOT-1001 · LOT-1002 · LOT-1003
공정 순서  LOAD_PORT → ETCH → PHOTO → CMP
```

---

## 파일 구조

```
amhs_simulator/
├── src/
│   ├── models.py      # 데이터 클래스 (Equipment, OHT, Lot, FailoverEvent)
│   ├── graph.py       # FAB 그래프 + Dijkstra 최단 경로
│   ├── scheduler.py   # Nearest OHT Scheduling + Failover 재할당
│   └── simulator.py   # Tick 루프 · 공정 처리 · 결과 출력
└── main.py            # 진입점 (argparse)
```

---

## 실행 방법

```bash
# 기본 실행 (seed=42, failover 확률 12%)
python main.py

# 시드 변경
python main.py --seed 7

# failover 확률 조정 (0.0 ~ 1.0)
python main.py --failover 0.05

# DEBUG 레벨 로그 (tick별 상세 이벤트)
python main.py --verbose

# 최대 tick 수 제한
python main.py --maxticks 500
```

### 출력 예시

```
=== FAB Graph (adjacency list) ===
  BUFFER_A   -> LOAD_PORT(2.0), ETCH-01(1.5), ETCH-02(2.0), BUFFER_B(3.0)
  ...

[LOT Summary]
  LOT ID       Total Time  Wait Ticks  Status
  LOT-1001             33           0  COMPLETE
  LOT-1002             53           0  COMPLETE
  LOT-1003             32           0  COMPLETE

  Average wait ticks per LOT : 0.00

[OHT Summary]
  OHT ID    Tasks  Total Dist  Final Pos   Status
  OHT-01        3        15.5  CMP-01      Idle
  OHT-02        3        20.0  CMP-02      Idle
  OHT-03        3        20.5  CMP-01      Idle

[Failover Events] (total=11)
  tick=  1 | OHT-02 ERROR | LOT-1002 (LOAD_PORT->ETCH-02) | reassigned->OHT-02
  ...
```

---

## 구현 알고리즘 설명

### 1. Dijkstra — FAB 최단 경로 탐색

**파일:** `src/graph.py`

FAB 내 OHT 레일망을 **무방향 가중치 그래프**로 모델링합니다.

```
LOAD_PORT ─(2.0)─ BUFFER_A ─(1.5)─ ETCH-01
                      │
                   (3.0)
                      │
                  BUFFER_B ─(1.5)─ PHOTO-01
                      │
                   (3.0)
                      │
                  BUFFER_C ─(1.5)─ CMP-01
```

노드: 설비 위치 + 버퍼 포인트 + LOAD/UNLOAD PORT  
엣지: OHT 레일 구간 (거리 단위)

**우선순위 큐(heapq)** 기반 Dijkstra로 임의의 두 노드 간 최단 거리와 경로를 O((V + E) log V)에 계산합니다.

```python
# 핵심 로직 (graph.py:dijkstra)
heap = [(0.0, source)]
while heap:
    d, u = heapq.heappop(heap)
    for v, w in self._adj[u]:
        if d + w < dist[v]:
            dist[v] = d + w
            heapq.heappush(heap, (dist[v], v))
```

OHT가 LOT을 픽업하러 이동하는 거리와 LOT을 목적 설비까지 운반하는 거리를 모두 Dijkstra로 계산하여 정확한 예상 소요 tick을 산출합니다.

---

### 2. Nearest OHT Scheduling

**파일:** `src/scheduler.py` — `nearest_idle_oht()`

LOT 운송 요청이 발생하면 **현재 위치 기준 가장 가까운 Idle OHT**를 선택합니다.

```
LOT 운송 요청 (from → to)
        │
        ▼
모든 Idle OHT에 대해
  dist(oht.position, from) 계산  ← Dijkstra 활용
        │
        ▼
최소 거리 OHT 선택
        │
        ▼
OHT: Idle → Busy
LOT: Waiting → InTransit
total_ticks = ceil(dist_pickup + dist_transit)
```

Idle OHT가 없으면 **Pending 큐**에 적재 후, 매 tick 자동 재시도합니다.  
이 방식은 실제 AMHS에서 사용하는 **Nearest Vehicle Dispatching** 정책과 동일한 원리입니다.

---

### 3. Failover — OHT 장애 및 재할당

**파일:** `src/scheduler.py` — `_handle_failover()`

매 tick마다 Busy 상태의 OHT에 대해 설정된 확률(`failover_prob`)로 장애를 시뮬레이션합니다.

```
tick 진행 중 OHT 장애 발생
        │
        ├─ OHT: Busy → Error → Idle (즉시 복구 모델)
        │
        ├─ LOT: InTransit → Waiting (출발지에서 재대기)
        │
        ├─ FailoverEvent 기록 (tick, oht_id, lot_id, from, to)
        │
        └─ 다른 Nearest Idle OHT에 즉시 재할당 시도
                │
                ├─ 성공 → LOT: Waiting → InTransit (재할당 OHT 기록)
                └─ 실패 → Pending 큐 추가 (다음 tick에 재시도)
```

모든 failover 이벤트는 `FailoverEvent` 데이터클래스로 저장되어 시뮬레이션 종료 후 전체 이력을 출력합니다.

---

### 4. Tick 기반 시뮬레이션 루프

**파일:** `src/simulator.py`

```
while tick < max_ticks:
    tick += 1
    [1] scheduler.tick()          ← OHT 이동 전진 + Failover 판정
    [2] start_processing_arrived() ← 도착 LOT 공정 시작 (sentinel -1 감지)
    [3] tick_processing_lots()    ← 공정 중 LOT 1tick 진행 → 완료 시 다음 공정 요청
    [4] if all LOTs DONE: break
```

공정 완료 후 즉시 다음 공정 운송 요청을 발행하므로 **LOT의 유휴 대기를 최소화**합니다.

---

## 설계 원칙

- **순수 Python:** 외부 라이브러리 의존 없이 핵심 알고리즘 직접 구현
- **모듈 분리:** 데이터 모델 / 그래프 / 스케줄러 / 시뮬레이터를 독립 레이어로 분리
- **재현성:** `random.Random(seed)` 로 동일 시드에서 항상 동일한 결과 보장
- **관찰 가능성:** Python `logging` 으로 모든 이벤트를 레벨별 기록
