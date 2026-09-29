import {
  CONTACT_LINKS,
  PORTFOLIO_URL,
  PRACTICES,
  PRODUCTS,
  type Product,
} from './content';
import { HeroPulse, PulseMark } from './PulseMark';

/** One product entry in the products ledger. */
function ProductEntry({ product, index }: { product: Product; index: number }) {
  const headingId = `product-${product.name.toLowerCase()}`;
  return (
    <li className="product">
      <article aria-labelledby={headingId}>
        <div className="product-head">
          <span className="product-index" aria-hidden="true">
            {String(index + 1).padStart(2, '0')}
          </span>
          <h3 id={headingId} className="product-name">
            {product.name}
          </h3>
          <p className="product-summary">{product.summary}</p>
        </div>
        <div className="product-detail">
          <p>{product.body}</p>
          <dl className="facts">
            {product.facts.map((fact) => (
              <div key={fact.label} className="fact">
                <dt>{fact.label}</dt>
                <dd>{fact.value}</dd>
              </div>
            ))}
          </dl>
          <a className="product-link" href={product.url}>
            Visit {product.host}
            <span aria-hidden="true"> →</span>
          </a>
        </div>
      </article>
    </li>
  );
}

/** The WebbPulse landing page. */
export default function App() {
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="site-header">
        <div className="wrap header-row">
          <a className="wordmark" href="/" aria-label="WebbPulse home">
            <PulseMark className="wordmark-mark" />
            <span>WebbPulse</span>
          </a>
          <nav aria-label="Sections">
            <ul className="nav-list">
              <li>
                <a href="#products">Products</a>
              </li>
              <li>
                <a href="#about">About</a>
              </li>
              <li>
                <a href="#contact">Contact</a>
              </li>
            </ul>
          </nav>
        </div>
      </header>

      <main id="main">
        <section className="hero wrap" aria-labelledby="hero-title">
          <p className="eyebrow">Software products</p>
          <h1 id="hero-title">WebbPulse builds and runs software products.</h1>
          <p className="lede">
            We design, build, deploy and support each product end to end, on
            infrastructure we run ourselves.
          </p>
          <HeroPulse className="hero-pulse" />
        </section>

        <section
          id="products"
          className="section wrap"
          aria-labelledby="products-title"
        >
          <h2 id="products-title" className="section-title">
            Products
          </h2>
          <ol className="products">
            {PRODUCTS.map((product, index) => (
              <ProductEntry
                key={product.name}
                product={product}
                index={index}
              />
            ))}
          </ol>
        </section>

        <section id="how" className="section wrap" aria-labelledby="how-title">
          <h2 id="how-title" className="section-title">
            How they are run
          </h2>
          <ul className="practices">
            {PRACTICES.map((practice) => (
              <li key={practice.title} className="practice">
                <h3>{practice.title}</h3>
                <p>{practice.body}</p>
              </li>
            ))}
          </ul>
        </section>

        <section
          id="about"
          className="section wrap split"
          aria-labelledby="about-title"
        >
          <h2 id="about-title" className="section-title">
            About
          </h2>
          <div className="prose">
            <p>
              WebbPulse was founded by Tyler Webb, a software engineer, and is
              not yet a registered company. It builds and operates its own
              products and adds new ones as they are ready.
            </p>
            <p>
              The founder&apos;s background and writing are on the portfolio
              site.
            </p>
            <a className="text-link" href={PORTFOLIO_URL}>
              portfolio.webbpulse.com<span aria-hidden="true"> →</span>
            </a>
          </div>
        </section>

        <section
          id="contact"
          className="section wrap split"
          aria-labelledby="contact-title"
        >
          <h2 id="contact-title" className="section-title">
            Contact
          </h2>
          <div className="prose">
            <p>
              Questions about a product, a bug report or anything else: email is
              the quickest way to reach us.
            </p>
            <ul className="contact-list">
              {CONTACT_LINKS.map((link) => (
                <li key={link.label}>
                  <span className="contact-label">{link.label}</span>
                  <a href={link.href}>{link.display}</a>
                </li>
              ))}
            </ul>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div className="wrap footer-row">
          <span className="wordmark small">
            <PulseMark className="wordmark-mark" />
            <span>WebbPulse</span>
          </span>
          <span>© WebbPulse</span>
        </div>
      </footer>
    </>
  );
}
