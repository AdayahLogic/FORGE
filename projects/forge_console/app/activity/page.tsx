import { ActivitySurface } from "../../components/activity-surface";
import { ExperienceNav } from "../../components/experience-nav";

export default function ActivityPage() {
  return (
    <main className="console-root">
      <div className="console-grid">
        <ExperienceNav activePath="/activity" />
        <section className="drawer-wrap">
          <ActivitySurface />
        </section>
      </div>
    </main>
  );
}
