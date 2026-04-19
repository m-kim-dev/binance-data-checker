import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  CandlestickSeries,
  HistogramSeries,
  createChart,
  createSeriesMarkers
} from "lightweight-charts";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";
const INTERVALS = ["1d", "4h", "1h", "15m"];
const RANGE_PRESETS = [
  { label: "1M", days: 30 },
  { label: "3M", days: 90 },
  { label: "1Y", days: 365 },
  { label: "All", days: 3650 }
];

function unixNow() {
  return Math.floor(Date.now() / 1000);
}

function query(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  return search.toString();
}

async function getJson(path) {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

function formatPrice(value) {
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: value > 100 ? 2 : 4
  }).format(value);
}

function formatVolume(value) {
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 2
  }).format(value);
}

function ChartPane({ candles, markers }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const candleSeriesRef = useRef(null);
  const volumeSeriesRef = useRef(null);
  const markerApiRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) return undefined;

    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { color: "#101418" },
        textColor: "#d7dde4",
        fontFamily:
          "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
      },
      grid: {
        vertLines: { color: "rgba(148, 163, 184, 0.12)" },
        horzLines: { color: "rgba(148, 163, 184, 0.12)" }
      },
      rightPriceScale: {
        borderColor: "rgba(148, 163, 184, 0.25)"
      },
      timeScale: {
        borderColor: "rgba(148, 163, 184, 0.25)",
        timeVisible: true,
        secondsVisible: false
      },
      crosshair: {
        mode: 1
      }
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#0f8b8d",
      downColor: "#c2410c",
      borderUpColor: "#0f8b8d",
      borderDownColor: "#c2410c",
      wickUpColor: "#49b6b8",
      wickDownColor: "#ef8a62"
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
      color: "rgba(148, 163, 184, 0.35)"
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.78,
        bottom: 0
      }
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;
    markerApiRef.current = createSeriesMarkers(candleSeries, []);

    return () => {
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      markerApiRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (
      !chartRef.current ||
      !candleSeriesRef.current ||
      !volumeSeriesRef.current ||
      !markerApiRef.current
    ) {
      return;
    }

    candleSeriesRef.current.setData(candles);
    markerApiRef.current.setMarkers(markers);
    volumeSeriesRef.current.setData(
      candles.map((item) => ({
        time: item.time,
        value: item.volume,
        color:
          item.close >= item.open
            ? "rgba(15, 139, 141, 0.35)"
            : "rgba(194, 65, 12, 0.35)"
      }))
    );
    chartRef.current.timeScale().fitContent();
  }, [candles, markers]);

  return <div className="chart-pane" ref={containerRef} />;
}

function RatioPane({ candles }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const candleSeriesRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) return undefined;

    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { color: "#101418" },
        textColor: "#d7dde4",
        fontFamily:
          "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
      },
      grid: {
        vertLines: { color: "rgba(148, 163, 184, 0.12)" },
        horzLines: { color: "rgba(148, 163, 184, 0.12)" }
      },
      rightPriceScale: {
        borderColor: "rgba(148, 163, 184, 0.25)"
      },
      timeScale: {
        borderColor: "rgba(148, 163, 184, 0.25)",
        timeVisible: true,
        secondsVisible: false
      }
    });
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#e5c07b",
      downColor: "#7aa2f7",
      borderUpColor: "#e5c07b",
      borderDownColor: "#7aa2f7",
      wickUpColor: "#f2d28a",
      wickDownColor: "#9bbcff",
      wickVisible: false
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;

    return () => {
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chartRef.current || !candleSeriesRef.current) return;
    candleSeriesRef.current.setData(candles);
    chartRef.current.timeScale().fitContent();
  }, [candles]);

  return <div className="chart-pane" ref={containerRef} />;
}

function App() {
  const [symbols, setSymbols] = useState([]);
  const [strategies, setStrategies] = useState([]);
  const [chartMode, setChartMode] = useState("candles");
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [quoteSymbol, setQuoteSymbol] = useState("ETHUSDT");
  const [interval, setInterval] = useState("1d");
  const [rangeDays, setRangeDays] = useState(90);
  const [strategyId, setStrategyId] = useState("ma_cross");
  const [candles, setCandles] = useState([]);
  const [ratioPoints, setRatioPoints] = useState([]);
  const [markers, setMarkers] = useState([]);
  const [latest, setLatest] = useState(null);
  const [status, setStatus] = useState("Loading market data");
  const [error, setError] = useState("");

  const candleQuery = useMemo(() => {
    const to = unixNow();
    const from = rangeDays >= 3650 ? undefined : to - rangeDays * 86400;
    return query({
      symbol,
      interval,
      from,
      to,
      limit: rangeDays >= 3650 ? 5000 : 1000,
      order: "asc"
    });
  }, [symbol, interval, rangeDays]);

  const ratioQuery = useMemo(() => {
    const to = unixNow();
    const from = rangeDays >= 3650 ? undefined : to - rangeDays * 86400;
    return query({
      base_symbol: symbol,
      quote_symbol: quoteSymbol,
      interval,
      from,
      to,
      limit: rangeDays >= 3650 ? 5000 : 1000,
      order: "asc"
    });
  }, [symbol, quoteSymbol, interval, rangeDays]);

  useEffect(() => {
    let cancelled = false;

    async function loadCatalog() {
      try {
        const [symbolData, strategyData] = await Promise.all([
          getJson("/symbols"),
          getJson("/strategies")
        ]);
        if (cancelled) return;
        setSymbols(symbolData.items ?? []);
        setStrategies(strategyData.items ?? []);
      } catch (err) {
        if (!cancelled) setError(`Catalog load failed: ${err.message}`);
      }
    }

    loadCatalog();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (symbol !== quoteSymbol) return;
    const replacement = symbols.find((item) => item.symbol !== symbol);
    if (replacement) {
      setQuoteSymbol(replacement.symbol);
    }
  }, [symbol, quoteSymbol, symbols]);

  useEffect(() => {
    let cancelled = false;

    async function loadChart() {
      setStatus("Loading chart");
      setError("");

      try {
        const [candleData, latestData, markerData, ratioData] = await Promise.all([
          getJson(`/candles?${candleQuery}`),
          getJson(`/candles/latest?${query({ symbol, interval })}`),
          getJson(
            `/strategies/${strategyId}/signals?${query({
              symbol,
              interval,
              from: rangeDays >= 3650 ? undefined : unixNow() - rangeDays * 86400,
              to: unixNow()
            })}`
          ),
          chartMode === "ratio"
            ? getJson(`/ratios?${ratioQuery}`)
            : Promise.resolve({ items: [] })
        ]);

        if (cancelled) return;
        setCandles(candleData.items ?? []);
        setLatest(latestData.item ?? null);
        setMarkers(markerData.items ?? []);
        setRatioPoints(ratioData.items ?? []);
        setStatus(chartMode === "ratio" ? "Ratio ready" : "Market data ready");
      } catch (err) {
        if (!cancelled) {
          setCandles([]);
          setRatioPoints([]);
          setLatest(null);
          setMarkers([]);
          setStatus("Request failed");
          setError(err.message);
        }
      }
    }

    loadChart();
    return () => {
      cancelled = true;
    };
  }, [candleQuery, ratioQuery, chartMode, symbol, interval, rangeDays, strategyId]);

  const activeCandle = latest ?? candles.at(-1);
  const activeRatio = ratioPoints.at(-1);
  const firstRatio = ratioPoints.at(0);
  const change = activeCandle
    ? ((activeCandle.close - activeCandle.open) / activeCandle.open) * 100
    : 0;
  const ratioChange =
    activeRatio && firstRatio ? ((activeRatio.close - firstRatio.open) / firstRatio.open) * 100 : 0;

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Algorithmic Trading UI</p>
          <h1>{symbol}</h1>
        </div>
        <div className="status-line">
          <span className={error ? "dot error-dot" : "dot"} />
          <span>{error || status}</span>
        </div>
      </header>

      <section className="modebar" aria-label="Chart mode">
        <button
          className={chartMode === "candles" ? "active" : ""}
          onClick={() => setChartMode("candles")}
          type="button"
        >
          Candles
        </button>
        <button
          className={chartMode === "ratio" ? "active" : ""}
          onClick={() => setChartMode("ratio")}
          type="button"
        >
          Ratio
        </button>
      </section>

      <section className="toolbar" aria-label="Chart controls">
        <label>
          <span>{chartMode === "ratio" ? "Numerator" : "Symbol"}</span>
          <select value={symbol} onChange={(event) => setSymbol(event.target.value)}>
            {(symbols.length ? symbols : [{ symbol: "BTCUSDT" }]).map((item) => (
              <option key={item.symbol} value={item.symbol}>
                {item.symbol}
              </option>
            ))}
          </select>
        </label>

        {chartMode === "ratio" && (
          <label>
            <span>Denominator</span>
            <select
              value={quoteSymbol}
              onChange={(event) => setQuoteSymbol(event.target.value)}
            >
              {(symbols.length ? symbols : [{ symbol: "ETHUSDT" }])
                .filter((item) => item.symbol !== symbol)
                .map((item) => (
                <option key={item.symbol} value={item.symbol}>
                  {item.symbol}
                </option>
                ))}
            </select>
          </label>
        )}

        <label>
          <span>Interval</span>
          <select value={interval} onChange={(event) => setInterval(event.target.value)}>
            {INTERVALS.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>Strategy</span>
          <select
            value={strategyId}
            onChange={(event) => setStrategyId(event.target.value)}
          >
            {(strategies.length
              ? strategies
              : [{ id: "ma_cross", name: "Moving Average Cross" }]
            ).map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>

        <div className="segmented" role="group" aria-label="Range">
          {RANGE_PRESETS.map((preset) => (
            <button
              className={preset.days === rangeDays ? "active" : ""}
              key={preset.label}
              onClick={() => setRangeDays(preset.days)}
              type="button"
            >
              {preset.label}
            </button>
          ))}
        </div>
      </section>

      <section className="metrics" aria-label="Market snapshot">
        <article>
          <span>{chartMode === "ratio" ? "Ratio" : "Last"}</span>
          <strong>
            {chartMode === "ratio"
              ? activeRatio
                ? formatPrice(activeRatio.close)
                : "-"
              : activeCandle
                ? formatPrice(activeCandle.close)
                : "-"}
          </strong>
        </article>
        <article>
          <span>{chartMode === "ratio" ? "Range" : "Session"}</span>
          <strong
            className={
              (chartMode === "ratio" ? ratioChange : change) >= 0 ? "positive" : "negative"
            }
          >
            {(chartMode === "ratio" ? ratioChange : change) >= 0 ? "+" : ""}
            {(chartMode === "ratio" ? ratioChange : change).toFixed(2)}%
          </strong>
        </article>
        <article>
          <span>{chartMode === "ratio" ? "Base Close" : "High"}</span>
          <strong>
            {chartMode === "ratio"
              ? activeRatio
                ? formatPrice(activeRatio.base_close)
                : "-"
              : activeCandle
                ? formatPrice(activeCandle.high)
                : "-"}
          </strong>
        </article>
        <article>
          <span>{chartMode === "ratio" ? "Quote Close" : "Low"}</span>
          <strong>
            {chartMode === "ratio"
              ? activeRatio
                ? formatPrice(activeRatio.quote_close)
                : "-"
              : activeCandle
                ? formatPrice(activeCandle.low)
                : "-"}
          </strong>
        </article>
        <article>
          <span>{chartMode === "ratio" ? "Pair" : "Volume"}</span>
          <strong>
            {chartMode === "ratio"
              ? `${symbol}/${quoteSymbol}`
              : activeCandle
                ? formatVolume(activeCandle.volume)
                : "-"}
          </strong>
        </article>
      </section>

      {chartMode === "ratio" ? (
        <RatioPane
          candles={ratioPoints.map(({ time, open, high, low, close }) => ({
            time,
            open,
            high,
            low,
            close
          }))}
        />
      ) : (
        <ChartPane candles={candles} markers={markers} />
      )}

      <section className="lower-grid">
        <div className="panel">
          <div className="panel-title">
            <h2>{chartMode === "ratio" ? "Pair" : "Signals"}</h2>
            <span>{chartMode === "ratio" ? `${ratioPoints.length} candles` : markers.length}</span>
          </div>
          {chartMode === "ratio" ? (
            <div className="pair-summary">
              <strong>{symbol}</strong>
              <span>long leg</span>
              <strong>{quoteSymbol}</strong>
              <span>short leg</span>
            </div>
          ) : (
            <div className="signal-list">
              {markers.map((marker) => (
              <div className="signal-row" key={`${marker.time}-${marker.text}`}>
                <span
                  className={
                    marker.shape === "arrowUp" ? "signal-side buy" : "signal-side sell"
                  }
                >
                  {marker.shape === "arrowUp" ? "Buy" : "Sell"}
                </span>
                <span>{marker.text ?? "Signal"}</span>
                <time>{new Date(marker.time * 1000).toISOString().slice(0, 10)}</time>
              </div>
              ))}
            </div>
          )}
        </div>

        <div className="panel">
          <div className="panel-title">
            <h2>API Request</h2>
            <span>{chartMode === "ratio" ? "Ratio" : "Candles"}</span>
          </div>
          <code>
            {chartMode === "ratio"
              ? `${API_BASE}/ratios?${ratioQuery}`
              : `${API_BASE}/candles?${candleQuery}`}
          </code>
        </div>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
