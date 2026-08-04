import { beforeEach, describe, expect, it, vi } from "vitest";

type PolicyAdmin = {
  addProjectClass: (panel: HTMLElement, projectClass: Record<string, unknown>) => HTMLElement;
  renderPolicy: (panel: HTMLElement, policy: Record<string, unknown>) => void;
  buildPayload: (panel: HTMLElement) => Record<string, unknown>;
  initAll: (root: HTMLElement) => void;
};

function panelMarkup() {
  document.body.innerHTML = `
    <meta name="csrf-token" content="csrf-123">
    <section data-project-annotation-policy-panel
             data-policy-url="/api/projects/7/annotation-policy"
             data-policy-save-url="/api/projects/7/annotation-policy"
             data-workspace-reload-url="/admin/upload-projects/7/workspace"
             data-workspace-reload-target="#project-detail-workspace">
      <span data-annotation-policy-status></span>
      <span data-annotation-policy-revision></span>
      <div data-annotation-policy-loading></div>
      <div data-annotation-policy-error class="d-none"></div>
      <form data-annotation-policy-form class="d-none">
        <input type="checkbox" data-annotation-policy-enabled>
        ${["box", "rect", "polygon", "brush_mask", "ellipse", "pyramid"].map((tool) =>
          `<input type="checkbox" value="${tool}" data-annotation-policy-tool>`
        ).join("")}
        <select data-annotation-default-localization>
          <option value="none">None</option>
          <option value="box">Box</option>
          <option value="segmentation">Segmentation</option>
          <option value="box_or_segmentation">Both</option>
        </select>
        <select data-annotation-default-preferred-tool></select>
        <div data-annotation-project-classes></div>
        <div data-annotation-project-classes-empty></div>
        <span data-annotation-policy-validation></span>
        <button type="submit" data-annotation-policy-submit>Save</button>
      </form>
    </section>`;
  return document.querySelector<HTMLElement>("[data-project-annotation-policy-panel]")!;
}

describe("project annotation policy editor", () => {
  let admin: PolicyAdmin;

  beforeEach(async () => {
    document.body.replaceChildren();
    vi.resetModules();
    delete (window as Window & { ProjectAnnotationPolicyAdmin?: PolicyAdmin }).ProjectAnnotationPolicyAdmin;
    await import("../../static/js/admin-project-annotations.js");
    admin = (window as Window & { ProjectAnnotationPolicyAdmin: PolicyAdmin }).ProjectAnnotationPolicyAdmin;
  });

  it("round-trips a simple project class row", () => {
    const panel = panelMarkup();
    admin.renderPolicy(panel, {
      enabled: true,
      revision: 3,
      enabled_tools: ["box", "polygon"],
      default_feature_policy: {
        localization: "box_or_segmentation",
        preferred_tool: "box",
        allowed_tools: ["box", "polygon"]
      },
      project_classes: [{
        id: 21,
        key: "lesion",
        localization: "box",
        multiple_instances: false,
        active: true
      }]
    });

    const classRow = panel.querySelector<HTMLElement>("[data-annotation-project-class-row]")!;
    expect(classRow.querySelector<HTMLInputElement>("[data-class-multiple]")!.checked).toBe(false);

    const payload = admin.buildPayload(panel) as {
      project_classes: Array<Record<string, unknown>>;
    };
    expect(payload.project_classes[0]).toMatchObject({
      id: 21,
      key: "lesion",
      localization: "box",
      multiple_instances: false
    });
    expect(payload).not.toHaveProperty("feature_overrides");
  });

  it("saves JSON with CSRF and refreshes the complete project workspace", async () => {
    const panel = panelMarkup();
    const savedPolicy = {
      enabled: true,
      revision: 1,
      enabled_tools: ["box"],
      default_feature_policy: {
        localization: "box_or_segmentation",
        preferred_tool: "box",
        allowed_tools: ["box"]
      },
      project_classes: []
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => savedPolicy })
      .mockResolvedValueOnce({ ok: true, json: async () => savedPolicy });
    vi.stubGlobal("fetch", fetchMock);
    const ajax = vi.fn();
    (window as Window & { htmx?: { ajax: typeof ajax } }).htmx = { ajax };

    admin.initAll(panel);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await vi.waitFor(() => expect(panel.querySelector("[data-annotation-policy-form]")?.classList.contains("d-none")).toBe(false));

    admin.addProjectClass(panel, {
      key: "lesion",
      localization: "box",
      multiple_instances: true,
      active: true
    });
    panel.querySelector<HTMLFormElement>("[data-annotation-policy-form]")!
      .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const saveRequest = fetchMock.mock.calls[1];
    expect(saveRequest[0]).toBe("/api/projects/7/annotation-policy");
    expect(saveRequest[1].method).toBe("PUT");
    expect(saveRequest[1].headers["X-CSRFToken"]).toBe("csrf-123");
    expect(JSON.parse(saveRequest[1].body).project_classes[0]).toMatchObject({
      key: "lesion",
      localization: "box",
      multiple_instances: true
    });
    await vi.waitFor(() => expect(ajax).toHaveBeenCalledWith(
      "GET",
      "/admin/upload-projects/7/workspace",
      { target: "#project-detail-workspace", swap: "innerHTML" }
    ));
  });
});
