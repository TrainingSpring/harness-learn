import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider, useTheme } from "./ThemeProvider";

function ThemeProbe() {
  const { theme, setTheme } = useTheme();
  return <button onClick={() => setTheme("light")}>{theme}</button>;
}

describe("ThemeProvider", () => {
  it("读取持久化主题并在修改后同步到根元素", async () => {
    localStorage.setItem("harness-theme", "dark");
    render(<ThemeProvider><ThemeProbe /></ThemeProvider>);

    expect(document.documentElement.dataset.theme).toBe("dark");
    await userEvent.click(screen.getByRole("button", { name: "dark" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem("harness-theme")).toBe("light");
  });
});
