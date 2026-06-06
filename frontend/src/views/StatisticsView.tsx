import { CollapsibleSection } from "../components/CollapsibleSection";
import { Statistics } from "../components/Statistics";
import { TradeListFilters } from "../types/trade";

interface StatisticsViewProps {
  onViewTradesFromInsight?: (filters: TradeListFilters) => void;
}

export function StatisticsView({ onViewTradesFromInsight }: StatisticsViewProps) {
  return (
    <section className="single-view-grid">
      <CollapsibleSection id="statistics-view" title="Statistics">
        <Statistics hideTitle onViewTradesFromInsight={onViewTradesFromInsight} />
      </CollapsibleSection>
    </section>
  );
}
