// Units (REF-02). First a list of unit groups, each with its units dimmed beside
// it; Enter opens a group: type a value, pick its unit from the dropdown (only
// that group's units), and every unit of the group is listed with the converted
// value. The selected row shows its evidence on the right.
// Shared by the Convert Units command and the generic ChemSidekick command.
import { Action, ActionPanel, Form, Icon, Keyboard, List, useNavigation } from "@raycast/api";
import { useCachedPromise, useCachedState } from "@raycast/utils";
import { type ReactNode, useState } from "react";
import { getTransport } from "../connection";
import {
  buildQuery,
  defaultUnit,
  formatKelvin,
  groupKeywords,
  groupSubtitle,
  isNumberOnly,
  rowDetail,
  type UnitChoiceGroup,
  unitChoices,
  type UnitResult,
  unitResult,
  type UnitRow,
} from "../lib/units";
import { ErrorView } from "./ErrorView";

const TEMPERATURES: { kelvin: string; title: string }[] = [
  { kelvin: "195.15", title: "−78 °C (dry ice)" },
  { kelvin: "273.15", title: "0 °C" },
  { kelvin: "298.15", title: "25 °C (standard)" },
  { kelvin: "310.15", title: "37 °C (body)" },
  { kelvin: "373.15", title: "100 °C" },
];

async function loadGroups(): Promise<UnitChoiceGroup[]> {
  const response = await getTransport().run("units", {}, { record: false });
  if (!response.ok) throw response.error; // ErrorInfo: shown by ErrorView
  return unitChoices(response.result);
}

type Outcome = { kind: "none" } | { kind: "input"; message: string } | { kind: "ok"; result: UnitResult };

async function convert(query: string | undefined, temperature: string, showAll: boolean): Promise<Outcome> {
  if (!query) return { kind: "none" };
  const response = await getTransport().run("units", { query, temperature, show_all: showAll }, { record: false });
  if (!response.ok) {
    // The text could not be read (e.g. "1.2.3"): say why and let the user keep typing.
    if (response.error.type === "input") return { kind: "input", message: response.error.message };
    throw response.error;
  }
  return { kind: "ok", result: unitResult(response.result) };
}

export function UnitsView({ initialText = "" }: { initialText?: string }) {
  // "1 eV to kcal/mol" typed after the command: convert it right away.
  if (initialText.trim() && !isNumberOnly(initialText)) return <ConversionView initialText={initialText} />;
  return <GroupList />;
}

function GroupList() {
  const { data: groups, isLoading, error, revalidate } = useCachedPromise(loadGroups, [], { keepPreviousData: true });
  if (error && !groups) return <ErrorView error={error} onRetry={revalidate} />;
  return (
    <List isLoading={isLoading} navigationTitle="Units" searchBarPlaceholder="Search unit groups or units (e.g. torr)">
      {groups?.map((g) => (
        <List.Item
          key={g.id}
          title={g.title}
          subtitle={groupSubtitle(g)}
          keywords={groupKeywords(g)}
          icon={Icon.Switch}
          actions={
            <ActionPanel>
              <Action.Push title={`Open ${g.title}`} icon={Icon.ArrowRight} target={<ConversionView group={g} />} />
              <Action.Push
                title="Try Example"
                icon={Icon.Wand}
                target={<ConversionView initialText={g.example} />}
                shortcut={{ modifiers: ["cmd", "shift"], key: "e" }}
              />
            </ActionPanel>
          }
        />
      ))}
    </List>
  );
}

function ConversionView({ group, initialText = "" }: { group?: UnitChoiceGroup; initialText?: string }) {
  const [text, setText] = useState(initialText);
  const first = group ? defaultUnit(group) : undefined;
  const [unitId, setUnitId] = useCachedState(`units-unit-${group?.id ?? "none"}`, first?.id ?? "");
  const [temperature, setTemperature] = useCachedState("units-temperature", "298.15");
  const [showAll, setShowAll] = useCachedState("units-show-all", false);

  const unit = group?.units.find((u) => u.id === unitId) ?? first;
  const query = group ? buildQuery(text, unit) : text.trim() || undefined;
  const {
    data: outcome,
    isLoading,
    error,
    revalidate,
  } = useCachedPromise(convert, [query, temperature, showAll], {
    keepPreviousData: true,
  });
  if (error) return <ErrorView error={error} onRetry={revalidate} />;

  const settings = (
    <>
      <ActionPanel.Submenu title="Set Temperature" icon={Icon.Temperature} shortcut={{ modifiers: ["cmd"], key: "t" }}>
        {TEMPERATURES.map((t) => (
          <Action
            key={t.kelvin}
            title={`${t.title} · ${t.kelvin} K`}
            icon={t.kelvin === temperature ? Icon.CheckCircle : Icon.Circle}
            onAction={() => setTemperature(t.kelvin)}
          />
        ))}
        <Action.Push
          title="Other Temperature…"
          icon={Icon.Pencil}
          target={<TemperatureForm current={temperature} onSubmit={setTemperature} />}
        />
      </ActionPanel.Submenu>
      <Action
        title={showAll ? "Show Common Units Only" : "Show All Units"}
        icon={showAll ? Icon.EyeDisabled : Icon.Eye}
        shortcut={{ modifiers: ["cmd", "shift"], key: "a" }}
        onAction={() => setShowAll(!showAll)}
      />
    </>
  );

  const common = group?.units.filter((u) => !u.more) ?? [];
  const more = group?.units.filter((u) => u.more) ?? [];
  return (
    <List
      isShowingDetail={outcome?.kind === "ok"}
      searchText={text}
      onSearchTextChange={setText}
      throttle
      isLoading={isLoading}
      navigationTitle={group?.title ?? "Units"}
      searchBarPlaceholder={unit ? `Value in ${unit.label} (e.g. 1, 2.5e-3)` : "1 eV to kcal/mol"}
      searchBarAccessory={
        group && (
          <List.Dropdown tooltip={`${group.title} unit of the value`} value={unit?.id} onChange={setUnitId}>
            <List.Dropdown.Section title={group.title}>
              {common.map((u) => (
                <List.Dropdown.Item key={u.id} value={u.id} title={u.label} keywords={[u.symbol, ...u.aliases]} />
              ))}
            </List.Dropdown.Section>
            {more.length > 0 && (
              <List.Dropdown.Section title="More">
                {more.map((u) => (
                  <List.Dropdown.Item key={u.id} value={u.id} title={u.label} keywords={[u.symbol, ...u.aliases]} />
                ))}
              </List.Dropdown.Section>
            )}
          </List.Dropdown>
        )
      }
    >
      {outcome?.kind === "input" && (
        <List.EmptyView
          icon={Icon.QuestionMarkCircle}
          title={outcome.message}
          description="Type a number, e.g. 1, 2.5e-3 or 1.2×10⁻³, and pick its unit on the right."
          actions={<ActionPanel>{settings}</ActionPanel>}
        />
      )}
      {outcome?.kind === "ok" &&
        outcome.result.warnings.map((w) => <List.Item key={w} icon={Icon.Warning} title={w} />)}
      {outcome?.kind === "ok" &&
        outcome.result.sections.map((section) => (
          <List.Section key={section.title} title={section.title}>
            {section.rows.map((row) => (
              <UnitItem key={row.key} result={outcome.result} row={row} settings={settings} />
            ))}
          </List.Section>
        ))}
    </List>
  );
}

function UnitItem({ result, row, settings }: { result: UnitResult; row: UnitRow; settings: ReactNode }) {
  const d = rowDetail(result, row);
  return (
    <List.Item
      title={row.value}
      subtitle={row.unit}
      keywords={[row.symbol]}
      detail={
        <List.Item.Detail
          markdown={`## ${d.heading}`}
          metadata={
            <List.Item.Detail.Metadata>
              {d.facts.map((f) => (
                <List.Item.Detail.Metadata.Label key={f.title} title={f.title} text={f.text} />
              ))}
              <List.Item.Detail.Metadata.Separator />
              {d.definitions.map((f) => (
                <List.Item.Detail.Metadata.Label key={f.title} title={f.title} text={f.text} />
              ))}
              {d.constants.length > 0 && <List.Item.Detail.Metadata.Separator />}
              {d.constants.map((f) => (
                <List.Item.Detail.Metadata.Label key={f.title} title={f.title} text={f.text} />
              ))}
              {d.sources.length > 0 && <List.Item.Detail.Metadata.Separator />}
              {d.sources.map((s, i) => (
                <List.Item.Detail.Metadata.Label key={s} title={i === 0 ? "Sources" : ""} text={s} />
              ))}
            </List.Item.Detail.Metadata>
          }
        />
      }
      actions={
        <ActionPanel>
          <ActionPanel.Section>
            <Action.CopyToClipboard title="Copy Value" content={row.value} />
            <Action.CopyToClipboard
              title="Copy Full Precision"
              content={row.full}
              shortcut={Keyboard.Shortcut.Common.Copy}
            />
            <Action.CopyToClipboard
              title="Copy with Unit"
              content={`${row.value} ${row.symbol}`}
              shortcut={{ modifiers: ["cmd"], key: "u" }}
            />
          </ActionPanel.Section>
          <ActionPanel.Section>{settings}</ActionPanel.Section>
        </ActionPanel>
      }
    />
  );
}

function TemperatureForm({ current, onSubmit }: { current: string; onSubmit: (kelvin: string) => void }) {
  const { pop } = useNavigation();
  return (
    <Form
      navigationTitle="Temperature for RT and kT"
      actions={
        <ActionPanel>
          <Action.SubmitForm
            title="Use Temperature"
            onSubmit={(values: { temperature: string }) => {
              onSubmit(values.temperature.trim() || "298.15");
              pop();
            }}
          />
        </ActionPanel>
      }
    >
      <Form.TextField
        id="temperature"
        title="Temperature"
        defaultValue={current}
        info="A number is in K. Add a unit for Celsius or Fahrenheit: 25 C, -78 °C, 77 F."
      />
      <Form.Description text={`Now: ${formatKelvinText(current)}`} />
    </Form>
  );
}

function formatKelvinText(value: string): string {
  const k = Number(value);
  return Number.isFinite(k) ? formatKelvin(k) : value;
}
