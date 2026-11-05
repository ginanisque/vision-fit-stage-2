interface LandingPageProps {
  onStart: () => void
}

const faqs = [
  {
    question: 'What do I need for a VisionFit capture?',
    answer: 'A phone or camera, a well-lit uncluttered space, fitted clothing, your height, and enough room to record one slow turn. Optional still photos are reference evidence for human review only.',
  },
  {
    question: 'What measurements can VisionFit support?',
    answer: 'The workflow is being built for garment measurements such as bust, waist, hip, shoulder and vertical body landmarks. Every result remains subject to quality checks and professional review.',
  },
  {
    question: 'Are my photos public?',
    answer: 'No. Captures are stored in private object storage and associated with your authenticated account. They are used for the measurement workflow you consent to.',
  },
  {
    question: 'Are my photos sent to another service?',
    answer: 'No. The current workflow does not send captures to Roboflow. Still photos are reference evidence only; experimental video candidates remain review-only.',
  },
  {
    question: 'Does VisionFit replace a professional fitting?',
    answer: 'No. VisionFit assists capture and measurement analysis. A trained reviewer may correct landmarks, request a new capture, or verify measurements before they are used for garment construction.',
  },
  {
    question: 'Why might I be asked to retake an image?',
    answer: 'Blur, poor lighting, incomplete framing, unsuitable posture, or an obscured body outline can make a measurement unreliable. The app explains what needs to be corrected.',
  },
]

export function LandingPage({ onStart }: LandingPageProps) {
  return (
    <main id="main-content" className="landing">
      <section className="hero" aria-labelledby="hero-title">
        <img className="hero-image" src="/assets/Vision_Fit_Website_Banner_1600x900.webp" alt="Ginani VisionFit digital fitting experience" />
        <div className="hero-shade" />
        <div className="hero-content">
          <span className="eyebrow">Made-to-measure, reimagined</span>
          <h1 id="hero-title">Better measurements begin with a better capture.</h1>
          <p>VisionFit guides you through secure photos and video so garment specialists can review body landmarks and create a useful measurement profile.</p>
          <div className="hero-actions">
            <button className="primary landing-cta" onClick={onStart}>Start VisionFit</button>
            <a className="text-link" href="#how-it-works">See how it works</a>
          </div>
        </div>
      </section>

      <section className="trust-strip" aria-label="VisionFit benefits">
        <div><strong>Guided</strong><span>Clear capture instructions</span></div>
        <div><strong>Private</strong><span>Authenticated, consent-led workflow</span></div>
        <div><strong>Reviewed</strong><span>Human oversight for measurement results</span></div>
      </section>

      <section id="how-it-works" className="content-section split-section">
        <div className="section-copy">
          <span className="eyebrow">How it works</span>
          <h2>A fitting workflow designed around you</h2>
          <p>VisionFit turns a careful capture into structured evidence for garment measurement. The service checks image quality and posture before results reach the review workspace.</p>
          <ol className="process-list">
            <li><span>01</span><div><strong>Prepare</strong><p>Read the privacy notice, give consent, and enter your height for scale.</p></div></li>
            <li><span>02</span><div><strong>Capture</strong><p>Record or upload one slow turn; VisionFit checks for front, side, and back views. Optional still photos are reference evidence for human review only.</p></div></li>
            <li><span>03</span><div><strong>Check</strong><p>Automated checks flag blur, lighting, framing, orientation, and posture concerns.</p></div></li>
            <li><span>04</span><div><strong>Review</strong><p>An authorised specialist reviews landmarks and the resulting measurement table.</p></div></li>
          </ol>
        </div>
        <figure className="feature-photo">
          <img src="/assets/ginani-vision-fit-models.jpg" alt="A model being measured by a garment professional" />
          <figcaption>Technology supports the process. Garment expertise completes it.</figcaption>
        </figure>
      </section>

      <section className="content-section measurement-section">
        <div>
          <span className="eyebrow">Built for garment making</span>
          <h2>From visible landmarks to usable measurements</h2>
        </div>
        <div className="measurement-grid">
          <article><span>01</span><h3>Body landmarks</h3><p>Reference points across front, side, and back views help locate shoulder, bust, waist, hip, knee, and floor levels.</p></article>
          <article><span>02</span><h3>Quality evidence</h3><p>Each capture carries checks and confidence evidence so uncertain results are not silently accepted.</p></article>
          <article><span>03</span><h3>Measurement tables</h3><p>Results are organised for review, correction, and eventual use in made-to-measure and pattern workflows.</p></article>
        </div>
      </section>

      <section className="content-section privacy-section">
        <div>
          <span className="eyebrow">Privacy by design</span>
          <h2>Your body data deserves careful handling.</h2>
        </div>
        <div>
          <p>VisionFit requires sign-in and explicit capture consent. Images and video are kept in private storage, while database records hold controlled references and analysis metadata. Captures are not sent to Roboflow; still photos are reviewer evidence only, and video-derived candidates require human tape confirmation. Captures and linked measurement results are deleted after 30 inactive days by default.</p>
          <p className="fine-print">Only submit images of yourself, or of a person who has knowingly consented. Measurement output is an estimate until it has been reviewed.</p>
        </div>
      </section>

      <section id="faq" className="content-section faq-section">
        <span className="eyebrow">Questions, answered</span>
        <h2>Frequently asked questions</h2>
        <div className="faq-list">
          {faqs.map((item) => (
            <details key={item.question}>
              <summary>{item.question}</summary>
              <p>{item.answer}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="final-cta">
        <img src="/assets/Vision_Fit_Logo_512.png" alt="" />
        <div><span className="eyebrow">Ready when you are</span><h2>Start your private VisionFit capture.</h2></div>
        <button className="primary landing-cta" onClick={onStart}>Open the app</button>
      </section>
    </main>
  )
}
