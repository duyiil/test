import { Empty } from "antd";
import * as echarts from "echarts";
import { useEffect, useRef } from "react";

export interface PassRatePoint {
  label: string;
  rate: number;
}

export function PassRateChart({ points }: { points: PassRatePoint[] }) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current || points.length === 0) return;
    const chart = echarts.init(ref.current);
    chart.setOption({
      tooltip: { trigger: "axis" },
      grid: { left: 48, right: 16, top: 24, bottom: 32 },
      xAxis: { type: "category", name: "时间", data: points.map((item) => item.label) },
      yAxis: { type: "value", name: "断言通过率", min: 0, max: 1 },
      series: [{ type: "line", name: "断言通过率", data: points.map((item) => item.rate) }],
    });
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [points]);

  if (points.length === 0) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无执行数据，不展示通过率" />;
  }
  return <div ref={ref} style={{ height: 280 }} />;
}
