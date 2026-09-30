import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { listStorageDirectories } from "../api";
import { StorageDirectoryPicker } from "./StorageDirectoryPicker";

vi.mock("../api", () => ({ listStorageDirectories: vi.fn() }));

it("浏览上级目录后可选择当前存储目录", async () => {
  const user = userEvent.setup();
  const onSelect = vi.fn();
  vi.mocked(listStorageDirectories)
    .mockResolvedValueOnce({ path: "/data", name: "data", parentPath: "/", directories: [{ path: "/data/cache", name: "cache" }] })
    .mockResolvedValueOnce({ path: "/", name: "/", parentPath: null, directories: [] });

  render(<StorageDirectoryPicker selectedPath="/data" onSelect={onSelect} onClose={vi.fn()} />);

  expect(await screen.findByDisplayValue("/data")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "返回上级目录" }));
  expect(await screen.findByDisplayValue("/")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "选择此目录" }));

  expect(onSelect).toHaveBeenCalledWith("/");
});
