export type MarketAsset = {
  symbol: string;
  name: string;
  icon: string;
  price: string;
  change: number;
  volume: string;
  status: "Up" | "Down";
  color: string;
};

export type MarketStat = {
  label: string;
  value: string;
  change: string;
  tone: "cyan" | "violet" | "amber" | "fuchsia";
  points: number[];
};

export const marketAssets: MarketAsset[] = [
  {
    symbol: "BTC",
    name: "Bitcoin",
    icon: "/icons/bitcoin.png",
    price: "$67,842.31",
    change: 2.45,
    volume: "$32.45B",
    status: "Up",
    color: "#f59e0b",
  },
  {
    symbol: "ETH",
    name: "Ethereum",
    icon: "/icons/ethereum.png",
    price: "$3,456.92",
    change: 1.67,
    volume: "$18.23B",
    status: "Up",
    color: "#6366f1",
  },
  {
    symbol: "BNB",
    name: "BNB",
    icon: "/icons/bnb.png",
    price: "$612.48",
    change: 0.84,
    volume: "$2.14B",
    status: "Up",
    color: "#f3ba2f",
  },
  {
    symbol: "SOL",
    name: "Solana",
    icon: "/icons/solana.png",
    price: "$142.73",
    change: 4.18,
    volume: "$4.92B",
    status: "Up",
    color: "#14f195",
  },
  {
    symbol: "XRP",
    name: "XRP",
    icon: "/icons/xrp.png",
    price: "$0.61",
    change: -0.74,
    volume: "$1.86B",
    status: "Down",
    color: "#64748b",
  },
  {
    symbol: "DOGE",
    name: "Dogecoin",
    icon: "/icons/dogecoin.png",
    price: "$0.13",
    change: 1.12,
    volume: "$1.09B",
    status: "Up",
    color: "#c2a633",
  },
  {
    symbol: "ADA",
    name: "Cardano",
    icon: "/icons/cardano.png",
    price: "$0.42",
    change: -0.38,
    volume: "$612.45M",
    status: "Down",
    color: "#2563eb",
  },
];

export const marketStats: MarketStat[] = [
  {
    label: "Total Market Cap",
    value: "$2.48T",
    change: "+3.24%",
    tone: "cyan",
    points: [14, 24, 21, 31, 25, 18, 22, 17, 19, 35, 58, 44],
  },
  {
    label: "24h Volume",
    value: "$128.76B",
    change: "+6.81%",
    tone: "violet",
    points: [18, 28, 36, 21, 16, 20, 42, 34, 24, 27, 23, 46],
  },
  {
    label: "Active Users",
    value: "154,321",
    change: "+12.4%",
    tone: "amber",
    points: [19, 32, 40, 28, 18, 26, 39, 43, 31, 24, 35, 49],
  },
  {
    label: "AI Signals Today",
    value: "1,247",
    change: "+23.7%",
    tone: "fuchsia",
    points: [17, 22, 34, 27, 18, 21, 32, 39, 28, 25, 31, 44],
  },
];

export const chartSeries = [
  91, 108, 99, 118, 132, 111, 104, 124, 146, 137, 152, 168, 154, 177, 184,
  173, 191, 203, 198, 216,
];

export const candleSeries = [
  { x: 30, open: 170, close: 132, high: 112, low: 186, volume: 58 },
  { x: 58, open: 138, close: 151, high: 126, low: 164, volume: 72 },
  { x: 86, open: 158, close: 122, high: 108, low: 176, volume: 64 },
  { x: 114, open: 127, close: 111, high: 96, low: 140, volume: 86 },
  { x: 142, open: 116, close: 139, high: 104, low: 152, volume: 49 },
  { x: 170, open: 146, close: 118, high: 100, low: 158, volume: 68 },
  { x: 198, open: 124, close: 96, high: 84, low: 136, volume: 94 },
  { x: 226, open: 102, close: 115, high: 88, low: 128, volume: 55 },
  { x: 254, open: 121, close: 88, high: 70, low: 132, volume: 76 },
  { x: 282, open: 94, close: 74, high: 58, low: 112, volume: 98 },
  { x: 310, open: 80, close: 102, high: 62, low: 118, volume: 65 },
  { x: 338, open: 108, close: 76, high: 60, low: 124, volume: 105 },
  { x: 366, open: 82, close: 64, high: 46, low: 100, volume: 118 },
  { x: 394, open: 70, close: 88, high: 54, low: 104, volume: 83 },
  { x: 422, open: 94, close: 58, high: 42, low: 110, volume: 126 },
];

export const features = [
  {
    title: "Real-time Market Data",
    description: "Live prices, liquidity, news, and alerts from global markets.",
    icon: "activity",
    tone: "cyan",
  },
  {
    title: "AI Risk Scoring",
    description: "Model-driven risk scores for trades, identity, and portfolio exposure.",
    icon: "brain",
    tone: "violet",
  },
  {
    title: "Portfolio Tracking",
    description: "Monitor performance, allocation, and drawdown in one dashboard.",
    icon: "pie",
    tone: "amber",
  },
  {
    title: "Secure eKYC",
    description: "Document OCR, liveness, face match, and deepfake checks.",
    icon: "shield",
    tone: "emerald",
  },
] as const;
