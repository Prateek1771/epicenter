/**
 * The UI's icon set: Phosphor, Light weight (design_reference: "minimal line-art SVGs in single-colour grey"; the
 * light stroke matches the 0.5px hairlines and 400–510 type weights). Every icon goes through this file, exported
 * under the names the markup already uses, so swapping the set or the weight is a change here only.
 *
 * `/ssr` entry: no React context, so the icons render in server and client components alike. Size comes from the
 * `size-*` class (CSS beats the SVG's width/height attributes), colour from `currentColor`.
 *
 * ponytail: each Phosphor icon carries all six weights' paths (~+33 kB first-load JS over lucide for these 55); if
 * that matters, inline the light paths as local SVG components behind these same names.
 */
import type { IconProps } from "@phosphor-icons/react";
import {
  ArrowCounterClockwiseIcon,
  ArrowDownIcon,
  ArrowLeftIcon,
  ArrowRightIcon,
  ArrowUpIcon,
  ArrowUUpLeftIcon,
  BellRingingIcon,
  BookOpenTextIcon,
  BroadcastIcon,
  CaretDownIcon,
  CaretRightIcon,
  CaretUpIcon,
  ChatTextIcon,
  CheckCircleIcon,
  CheckIcon,
  CircleDashedIcon,
  CircleNotchIcon,
  ClockCounterClockwiseIcon,
  ClockIcon,
  CopyIcon,
  CrosshairIcon,
  CrownIcon,
  DownloadSimpleIcon,
  EyeSlashIcon,
  FlaskIcon,
  FloppyDiskIcon,
  GaugeIcon,
  GitCommitIcon,
  InfoIcon as PInfoIcon,
  OctagonIcon,
  GitForkIcon,
  GithubLogoIcon,
  GraphIcon,
  LightbulbIcon,
  MagnifyingGlassIcon,
  NotePencilIcon,
  PaperPlaneTiltIcon,
  PauseIcon,
  PlayCircleIcon,
  PlayIcon,
  ProhibitIcon,
  PulseIcon,
  QuestionIcon,
  ReceiptIcon,
  RecordIcon,
  ShieldCheckIcon,
  SparkleIcon,
  TableIcon,
  TargetIcon,
  UsersIcon,
  WarningCircleIcon,
  WarningIcon,
  WifiSlashIcon,
  WrenchIcon,
  XCircleIcon,
  XIcon as PXIcon,
} from "@phosphor-icons/react/ssr";
import type { ComponentType } from "react";

export type Icon = ComponentType<IconProps>;

const light = (I: Icon, name: string): Icon => {
  const C = (p: IconProps) => <I weight="light" {...p} />;
  C.displayName = name;
  return C;
};

export const Activity = light(PulseIcon, "Activity");
export const AlertTriangle = light(WarningIcon, "AlertTriangle");
export const TriangleAlert = AlertTriangle;
export const ArrowDown = light(ArrowDownIcon, "ArrowDown");
export const ArrowLeft = light(ArrowLeftIcon, "ArrowLeft");
export const ArrowRight = light(ArrowRightIcon, "ArrowRight");
export const ArrowUp = light(ArrowUpIcon, "ArrowUp");
export const BellRing = light(BellRingingIcon, "BellRing");
export const BookOpenCheck = light(BookOpenTextIcon, "BookOpenCheck");
export const Check = light(CheckIcon, "Check");
export const ChevronDown = light(CaretDownIcon, "ChevronDown");
export const ChevronRight = light(CaretRightIcon, "ChevronRight");
export const ChevronUp = light(CaretUpIcon, "ChevronUp");
export const CircleAlert = light(WarningCircleIcon, "CircleAlert");
export const CircleCheck = light(CheckCircleIcon, "CircleCheck");
export const CircleDashed = light(CircleDashedIcon, "CircleDashed");
export const CircleDot = light(RecordIcon, "CircleDot");
export const CircleHelp = light(QuestionIcon, "CircleHelp");
export const HelpCircle = CircleHelp;
export const CircleSlash = light(ProhibitIcon, "CircleSlash");
export const CircleX = light(XCircleIcon, "CircleX");
export const Clock = light(ClockIcon, "Clock");
export const Copy = light(CopyIcon, "Copy");
export const Crosshair = light(CrosshairIcon, "Crosshair");
export const Crown = light(CrownIcon, "Crown");
export const Download = light(DownloadSimpleIcon, "Download");
export const EyeOff = light(EyeSlashIcon, "EyeOff");
export const FlaskConical = light(FlaskIcon, "FlaskConical");
export const Gauge = light(GaugeIcon, "Gauge");
export const GitCommitHorizontal = light(GitCommitIcon, "GitCommitHorizontal");
export const GitFork = light(GitForkIcon, "GitFork");
export const Github = light(GithubLogoIcon, "Github");
export const History = light(ClockCounterClockwiseIcon, "History");
export const Lightbulb = light(LightbulbIcon, "Lightbulb");
export const Loader2 = light(CircleNotchIcon, "Loader2");
export const MessageSquarePlus = light(NotePencilIcon, "MessageSquarePlus");
export const MessageSquareText = light(ChatTextIcon, "MessageSquareText");
export const Network = light(GraphIcon, "Network");
export const Pause = light(PauseIcon, "Pause");
export const Play = light(PlayIcon, "Play");
export const PlayCircle = light(PlayCircleIcon, "PlayCircle");
export const Radar = light(TargetIcon, "Radar");
export const Radio = light(BroadcastIcon, "Radio");
export const Receipt = light(ReceiptIcon, "Receipt");
export const RotateCcw = light(ArrowCounterClockwiseIcon, "RotateCcw");
export const Save = light(FloppyDiskIcon, "Save");
export const Search = light(MagnifyingGlassIcon, "Search");
export const Send = light(PaperPlaneTiltIcon, "Send");
export const ShieldCheck = light(ShieldCheckIcon, "ShieldCheck");
export const Sparkles = light(SparkleIcon, "Sparkles");
export const Table2 = light(TableIcon, "Table2");
export const Undo2 = light(ArrowUUpLeftIcon, "Undo2");
export const Users = light(UsersIcon, "Users");
export const WifiOff = light(WifiSlashIcon, "WifiOff");
export const Wrench = light(WrenchIcon, "Wrench");
export const X = light(PXIcon, "X");
export const Info = light(PInfoIcon, "Info");
export const OctagonX = light(OctagonIcon, "OctagonX");
// shadcn primitives (and the toaster) use the *Icon names
export {
  Check as CheckIcon,
  ChevronDown as ChevronDownIcon,
  ChevronUp as ChevronUpIcon,
  CircleCheck as CircleCheckIcon,
  Info as InfoIcon,
  Loader2 as Loader2Icon,
  OctagonX as OctagonXIcon,
  Search as SearchIcon,
  TriangleAlert as TriangleAlertIcon,
  X as XIcon,
};
