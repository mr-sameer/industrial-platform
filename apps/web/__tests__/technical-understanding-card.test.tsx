import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TechnicalUnderstandingCard, type TechnicalUnderstanding } from "@/components/consult/TechnicalUnderstandingCard";

const EMPTY: TechnicalUnderstanding = { criteria: [], ambiguous: [], unsupported: [], regionalPreference: [] };

describe("TechnicalUnderstandingCard", () => {
  it("renders nothing when there is genuinely nothing to say", () => {
    const { container } = render(<TechnicalUnderstandingCard understanding={EMPTY} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders a resolved criterion as a confirmed (checkmark) line", () => {
    render(<TechnicalUnderstandingCard understanding={{ ...EMPTY, criteria: ["Flow Rate: >= 15 m3/hr"] }} />);
    expect(screen.getByText("Flow Rate: >= 15 m3/hr")).toBeTruthy();
  });

  it("renders an ambiguous mention as a warning, never as a confirmed criterion", () => {
    render(<TechnicalUnderstandingCard understanding={{ ...EMPTY, ambiguous: ["Motor Power"] }} />);
    expect(screen.getByText(/Motor Power was mentioned but couldn't be parsed/)).toBeTruthy();
  });

  it("renders an unsupported concept as a warning naming what isn't matchable", () => {
    render(
      <TechnicalUnderstandingCard
        understanding={{ ...EMPTY, unsupported: ["Material / wetted-parts construction"] }}
      />
    );
    expect(screen.getByText(/Material \/ wetted-parts construction requirement is not currently matchable/)).toBeTruthy();
  });

  it("renders a noted regional preference without implying it was applied as a filter", () => {
    render(
      <TechnicalUnderstandingCard
        understanding={{ ...EMPTY, regionalPreference: ["Gujarat", "Maharashtra", "Tamil Nadu"] }}
      />
    );
    expect(screen.getByText(/Regional preference noted: Gujarat, Maharashtra, Tamil Nadu/)).toBeTruthy();
  });

  it("renders every category together for the full real buyer pilot understanding", () => {
    render(
      <TechnicalUnderstandingCard
        understanding={{
          criteria: ["Flow Rate: >= 15 m3/hr", "Head: >= 150 m", "Motor Power: <= 15 kW", "Pump Type: = Vertical Multistage Centrifugal Pump"],
          ambiguous: [],
          unsupported: ["Material / wetted-parts construction"],
          regionalPreference: ["Gujarat", "Maharashtra", "Tamil Nadu"],
        }}
      />
    );
    expect(screen.getByText("Flow Rate: >= 15 m3/hr")).toBeTruthy();
    expect(screen.getByText("Head: >= 150 m")).toBeTruthy();
    expect(screen.getByText("Motor Power: <= 15 kW")).toBeTruthy();
    expect(screen.getByText("Pump Type: = Vertical Multistage Centrifugal Pump")).toBeTruthy();
    expect(screen.getByText(/Regional preference noted/)).toBeTruthy();
    expect(screen.getByText(/not currently matchable/)).toBeTruthy();
  });
});
