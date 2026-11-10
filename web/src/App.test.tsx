import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("r-bridge shell", () => {
  it("renders the brand, the scaffold badge and the relayer dependency", () => {
    render(<App />);
    expect(screen.getByText("r-bridge")).toBeInTheDocument();
    expect(screen.getByText("scaffold")).toBeInTheDocument();
    expect(screen.getAllByText(/relayer/i).length).toBeGreaterThan(0);
  });

  it("shows the canonical chain-qualified assets", () => {
    render(<App />);
    expect(screen.getByText("wUSDT.eth")).toBeInTheDocument();
    expect(screen.getByText("wUSDT.trx")).toBeInTheDocument();
    expect(screen.getByText("wUSDC.noble")).toBeInTheDocument();
  });
});
