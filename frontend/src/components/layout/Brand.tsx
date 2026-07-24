import { Link } from "react-router-dom";
import styles from "./Brand.module.css";

export function Brand() {
  return (
    <Link to="/" className={styles.brand}>
      <svg className={styles.mark} viewBox="0 0 100 100" aria-hidden="true">
        <g fill="none" stroke="#c9b4e6" strokeWidth="4">
          <rect x="30" y="10" width="34" height="34" transform="rotate(45 47 27)" />
          <rect x="10" y="30" width="34" height="34" transform="rotate(45 27 47)" />
          <rect x="50" y="30" width="34" height="34" transform="rotate(45 67 47)" />
          <rect x="30" y="50" width="34" height="34" transform="rotate(45 47 67)" />
        </g>
        <rect
          x="32"
          y="32"
          width="30"
          height="30"
          transform="rotate(45 47 47)"
          fill="none"
          stroke="#7228b8"
          strokeWidth="6"
        />
      </svg>
      <span className={styles.name}>
        Boj<b>AI</b>
      </span>
    </Link>
  );
}
