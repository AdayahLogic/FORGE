import { ExperienceNav } from "../../components/experience-nav";
import { OperatorConsoleSurface } from "../../components/operator-console-surface";

export default function ConsolePage() {
  return (
    <main className="console-root">
      <div className="console-grid">
        <ExperienceNav activePath="/console" />
        <section className="drawer-wrap">
          <OperatorConsoleSurface />
        </section>
      </div>
    </main>
  );
}
