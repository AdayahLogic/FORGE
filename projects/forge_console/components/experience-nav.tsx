import Link from "next/link";

type ExperienceNavProps = {
  activePath: "/console" | "/activity" | "/";
};

export function ExperienceNav({ activePath }: ExperienceNavProps) {
  return (
    <section className="panel top-band">
      <div className="section-title">
        <div>
          <div className="eyebrow">Forge Experience Layer</div>
          <h2>Operator Console + Live Activity Surface</h2>
        </div>
        <div className="chip-row">
          <Link
            className={`action-button ${activePath === "/console" ? "selected-surface" : ""}`}
            href="/console"
          >
            Console
          </Link>
          <Link
            className={`action-button ${activePath === "/activity" ? "selected-surface" : ""}`}
            href="/activity"
          >
            Activity
          </Link>
          <Link
            className={`action-button ${activePath === "/" ? "selected-surface" : ""}`}
            href="/"
          >
            Existing Surface
          </Link>
        </div>
      </div>
    </section>
  );
}
