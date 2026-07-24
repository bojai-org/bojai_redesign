import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import styles from "./Tabs.module.css";

interface TabButtonBaseProps {
  label: string;
  icon?: ReactNode;
}

interface TabButtonLinkProps extends TabButtonBaseProps {
  to: string;
  active?: never;
  onClick?: never;
}

interface TabButtonButtonProps extends TabButtonBaseProps {
  to?: undefined;
  active: boolean;
  onClick: () => void;
}

export type TabButtonProps = TabButtonLinkProps | TabButtonButtonProps;

export function TabButton(props: TabButtonProps) {
  if (props.to) {
    return (
      <NavLink
        to={props.to}
        end
        className={({ isActive }) =>
          isActive ? `${styles.tab} ${styles.active}` : styles.tab
        }
      >
        {props.icon}
        {props.label}
      </NavLink>
    );
  }

  return (
    <button
      type="button"
      className={props.active ? `${styles.tab} ${styles.active}` : styles.tab}
      onClick={props.onClick}
    >
      {props.icon}
      {props.label}
    </button>
  );
}
